"""
train_model.py
--------------
Trains the GreenChain CatBoost quantile regression emissions estimator by default.

Model output: tCO2e per $1M spend (log-transformed during training).
Three models are trained (one per quantile): q10, q50, q90.
The 10th / 90th percentile form the confidence interval shown in the UI.

Validation metric: Spearman rank correlation on held-out country-industry pairs.
(Rank ordering matters more than absolute accuracy.)

Run:
    python ml/train_model.py                    # CatBoost (default)
    python ml/train_model.py --model xgboost    # explicit legacy backend
Outputs:
    models/catboost_q10.cbm
    models/catboost_q50.cbm
    models/catboost_q90.cbm
    models/feature_columns.json
    models/catboost_feature_columns.json
    models/model_manifest.json
    models/training_report.txt
"""

import argparse
import json
import os
import sys
import time
from typing import Any, cast

import joblib
import numpy as np
import pandas as pd
from scipy import stats
from sklearn.model_selection import GroupShuffleSplit

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from ml.reference_data import COUNTRY_EMISSION_MULTIPLIER

_THIS_DIR  = os.path.dirname(os.path.abspath(__file__))
_ROOT      = os.path.dirname(_THIS_DIR)
RAW_CSV    = os.path.join(_ROOT, "data", "raw", "cdp_synthetic.csv")
MODEL_DIR  = os.path.join(_ROOT, "models")

QUANTILES = [0.10, 0.50, 0.90]
SEED      = 42


# ---------------------------------------------------------------------------
# 1. Load & clean
# ---------------------------------------------------------------------------
def load_data() -> pd.DataFrame:
    df = pd.read_csv(RAW_CSV)
    print(f"Loaded {len(df)} records, {df['country_iso'].nunique()} countries, "
          f"{df['naics4'].nunique()} NAICS codes")

    # Drop extreme outliers (>99.5th percentile) — likely reporting errors in real CDP
    p995 = df["tco2e_per_usdm"].quantile(0.995)
    df = cast(pd.DataFrame, df[df["tco2e_per_usdm"] <= p995]).copy()
    print(f"After outlier removal: {len(df)} records")
    return df


# ---------------------------------------------------------------------------
# 2. Feature engineering
# ---------------------------------------------------------------------------
def build_features(df: pd.DataFrame, backend: str = "catboost"):
    """
    Returns X (DataFrame), y (log-transformed target), feature_names list.
    Features:
      - log_revenue            : continuous
      - log_grid               : continuous (log of gCO2/kWh)
      - year_offset            : continuous (years since 2018)
      - ctry_mult              : continuous (country manufacturing multiplier)
      - log_useeio_base        : continuous (log of real USEEIO sector intensity)
                                 KEY — directly encodes industry emission level
      - useeio_x_grid          : interaction log_useeio_base × log_grid
                                 KEY for within-country ranking: steel mill in dirty-grid
                                 country >> software in same country
      - useeio_x_ctry          : interaction log_useeio_base × ctry_mult
      - country_iso            : CatBoost categorical (one-hot for XGBoost)
      - naics2                 : CatBoost categorical (one-hot for XGBoost)
    """
    from ml.reference_data import NAICS_DETAIL

    df = df.copy()

    # Log-transform target (heavy right skew)
    df["log_target"] = np.log(df["tco2e_per_usdm"].clip(lower=0.01))

    # USEEIO base intensity as continuous feature (real EPA values, 1016 codes)
    df["useeio_base"] = df["naics4"].map(
        lambda n: NAICS_DETAIL.get(str(n), (None, None, 500_000))[2]
    )
    df["log_useeio_base"] = np.log(df["useeio_base"].clip(lower=1_000))

    # Other continuous features
    df["year_offset"] = df["year"] - 2018
    df["ctry_mult"]   = df["country_iso"].map(
                            lambda c: COUNTRY_EMISSION_MULTIPLIER.get(c, 1.0))
    df["log_grid"]    = np.log(df["grid_intensity_gco2_kwh"].clip(lower=5))

    # Interaction features — key for within-country industry discrimination
    # A steel mill in China (high useeio × dirty grid) >> software in China
    df["useeio_x_grid"]  = df["log_useeio_base"] * df["log_grid"]
    df["useeio_x_ctry"]  = df["log_useeio_base"] * df["ctry_mult"]

    continuous_cols = ["log_revenue", "log_grid", "year_offset",
                       "ctry_mult", "log_useeio_base",
                       "useeio_x_grid", "useeio_x_ctry"]

    if backend == "catboost":
        # Preserve the two categorical signals so CatBoost can learn ordered
        # target statistics instead of seeing a sparse one-hot expansion.
        X = df[continuous_cols + ["country_iso", "naics2"]].reset_index(drop=True).copy()
        X["country_iso"] = X["country_iso"].astype(str)
        X["naics2"] = X["naics2"].astype(str)
    else:
        country_dummies = pd.get_dummies(df["country_iso"], prefix="ctry", drop_first=False)
        naics_dummies = pd.get_dummies(df["naics2"], prefix="nac", drop_first=False)
        X = pd.concat([
            df[continuous_cols].reset_index(drop=True),
            country_dummies.reset_index(drop=True),
            naics_dummies.reset_index(drop=True),
        ], axis=1)

    y = df["log_target"].values
    return X, y, df


# ---------------------------------------------------------------------------
# 3. Train-test split (group split by country-naics2 pair)
# ---------------------------------------------------------------------------
def split_data(X, y, df):
    """
    Hold out 15% of country-naics2 pairs to test rank generalisation.
    This mirrors the real CDP use-case where we might see new country-industry combos.
    """
    groups = df["country_iso"].astype(str) + "_" + df["naics2"].astype(str)
    gss = GroupShuffleSplit(n_splits=1, test_size=0.15, random_state=SEED)
    train_idx, test_idx = next(gss.split(X, y, groups=groups.values))
    return X.iloc[train_idx], X.iloc[test_idx], y[train_idx], y[test_idx], df.iloc[test_idx]


# ---------------------------------------------------------------------------
# 4. Train backend-selected quantile models (CatBoost by default)
# ---------------------------------------------------------------------------
def train_quantile_model(X_train, y_train, quantile: float, backend: str = "catboost"):
    """Train one emissions quantile model; CatBoost is the default backend."""
    if backend == "catboost":
        from catboost import CatBoostRegressor

        model = CatBoostRegressor(
            loss_function=f"Quantile:alpha={quantile}",
            iterations=1000,
            depth=8,
            learning_rate=0.035,
            l2_leaf_reg=5.0,
            random_seed=SEED,
            thread_count=-1,
            verbose=False,
            allow_writing_files=False,
        )
        model.fit(X_train, y_train, cat_features=["country_iso", "naics2"], verbose=False)
        return model
    if backend == "xgboost":
        import xgboost as xgb

        model = xgb.XGBRegressor(
            objective="reg:quantileerror", quantile_alpha=quantile,
            n_estimators=600, max_depth=7, learning_rate=0.04,
            subsample=0.85, colsample_bytree=0.75, min_child_weight=3,
            reg_alpha=0.05, reg_lambda=1.5, random_state=SEED,
            n_jobs=-1, tree_method="hist",
        )
        model.fit(X_train, y_train, eval_set=[(X_train, y_train)], verbose=False)
        return model
    raise ValueError(f"Unsupported model backend: {backend}")


# ---------------------------------------------------------------------------
# 5. Evaluation
# ---------------------------------------------------------------------------
def evaluate(model_q50, X_test, y_test, df_test):
    pred_log = model_q50.predict(X_test)
    pred     = np.exp(pred_log)
    actual   = np.exp(y_test)

    # Spearman on full test set
    # scipy's result type doesn't declare .statistic/.pvalue for type checkers.
    overall: Any = stats.spearmanr(pred, actual)
    rho, p   = float(overall.statistic), float(overall.pvalue)

    # Spearman within each country-naics2 group (pairwise rank correctness)
    df_test = df_test.copy()
    df_test["pred"]   = pred
    df_test["actual"] = actual
    group_rhos = []
    for grp, sub in df_test.groupby(["country_iso", "naics2"]):
        if len(sub) >= 4:
            group_result: Any = stats.spearmanr(sub["pred"], sub["actual"])
            r = float(group_result.statistic)
            if not np.isnan(r):
                group_rhos.append(r)

    mean_group_rho = float(np.mean(group_rhos)) if group_rhos else float("nan")

    # MAE on log scale
    mae_log = float(np.mean(np.abs(pred_log - y_test)))
    # Median absolute percentage error
    mape    = float(np.median(np.abs(pred - actual) / actual) * 100)

    metrics = {
        "spearman_rho_overall":    round(rho, 4),
        "spearman_p_value":        round(float(p), 6),
        "mean_group_spearman":     round(mean_group_rho, 4),
        "mae_log_scale":           round(mae_log, 4),
        "median_abs_pct_err":      round(mape, 1),
        "n_test":                  len(X_test),
        "n_groups_evaluated":      len(group_rhos),
    }
    return metrics


# ---------------------------------------------------------------------------
# 6. Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Train GreenChain emissions quantile models")
    parser.add_argument(
        "--model", choices=("catboost", "xgboost"), default="catboost",
        help="Training backend (default: catboost; xgboost remains available explicitly)",
    )
    args = parser.parse_args()
    backend = args.model
    os.makedirs(MODEL_DIR, exist_ok=True)

    # ── Load ──
    df = load_data()
    X, y, df_feat = build_features(df, backend=backend)

    # ── Split ──
    X_train, X_test, y_train, y_test, df_test = split_data(X, y, df_feat)
    print(f"Train: {len(X_train)}, Test: {len(X_test)}")
    print(f"Feature matrix: {X_train.shape[1]} columns")

    # ── Save feature column list for inference ──
    feature_cols = list(X_train.columns)
    # Preserve the original XGBoost schema before replacing the legacy shared
    # feature file, so the explicit fallback remains loadable after CatBoost training.
    xgb_features_path = os.path.join(MODEL_DIR, "xgboost_feature_columns.json")
    legacy_features_path = os.path.join(MODEL_DIR, "feature_columns.json")
    if backend == "catboost" and not os.path.isfile(xgb_features_path) and os.path.isfile(legacy_features_path):
        with open(legacy_features_path, encoding="utf-8") as f:
            legacy_features = json.load(f)
        with open(xgb_features_path, "w", encoding="utf-8") as f:
            json.dump(legacy_features, f, indent=2)
    with open(os.path.join(MODEL_DIR, f"{backend}_feature_columns.json"), "w", encoding="utf-8") as f:
        json.dump(feature_cols, f, indent=2)
    with open(legacy_features_path, "w", encoding="utf-8") as f:
        json.dump(feature_cols, f, indent=2)

    # ── Train 3 quantile models ──
    models = {}
    for q in QUANTILES:
        print(f"\nTraining {backend.title()} q={q:.2f}...", end=" ", flush=True)
        t0 = time.time()
        model = train_quantile_model(X_train, y_train, quantile=q, backend=backend)
        elapsed = time.time() - t0
        fname = os.path.join(MODEL_DIR, f"{backend}_q{int(q*100):02d}")
        if backend == "catboost":
            fname += ".cbm"
            model.save_model(fname, format="cbm")
        else:
            fname += ".joblib"
            joblib.dump(model, fname)
            model.save_model(os.path.join(MODEL_DIR, f"xgb_q{int(q*100):02d}.ubj"))
        models[q] = model
        print(f"done ({elapsed:.1f}s) → {fname}")

    # ── Evaluate median model ──
    print("\nEvaluating q=0.50 model on held-out country-industry pairs...")
    metrics = evaluate(models[0.50], X_test, y_test, df_test)

    report = []
    report.append("=" * 60)
    report.append(f"GreenChain {backend.title()} Emissions Model — Training Report")
    report.append("Backend is selected by --model; default is CatBoost with native country/industry categoricals.")
    report.append("=" * 60)
    report.append(f"Training records : {len(X_train)}")
    report.append(f"Test records     : {len(X_test)}")
    report.append(f"Features         : {X_train.shape[1]}")
    report.append("")
    report.append("── Validation Metrics (median model, q=0.50) ──")
    for k, v in metrics.items():
        report.append(f"  {k:<35} {v}")
    report.append("")
    report.append("── Key insight ──")
    report.append("  The source is cdp_synthetic.csv; metrics do not establish real-world accuracy.")
    report.append("  CatBoost is the default challenger, not proven superior to XGBoost until both")
    report.append("  are trained and compared on the same held-out split.")
    report.append("")
    report.append("── Feature importance (top 10, q50 model) ──")

    if backend == "catboost":
        imp = dict(zip(feature_cols, models[0.50].get_feature_importance()))
    else:
        imp = models[0.50].get_booster().get_score(importance_type="gain")
    top10 = sorted(imp.items(), key=lambda x: -x[1])[:10]
    for feat, score in top10:
        report.append(f"  {feat:<35} {score:.1f}")

    report_text = "\n".join(report)
    print("\n" + report_text)

    with open(os.path.join(MODEL_DIR, "training_report.txt"), "w") as f:
        f.write(report_text)

    manifest_path = os.path.join(MODEL_DIR, "model_manifest.json")
    manifest_tmp = manifest_path + ".tmp"
    with open(manifest_tmp, "w", encoding="utf-8") as f:
        json.dump({"backend": backend, "quantiles": QUANTILES, "feature_count": len(feature_cols)}, f, indent=2)
    os.replace(manifest_tmp, manifest_path)

    print(f"\nAll models saved to {MODEL_DIR}/")
    return metrics


if __name__ == "__main__":
    main()
