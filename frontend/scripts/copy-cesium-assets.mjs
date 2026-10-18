// Copies CesiumJS's runtime assets (prebuilt bundle, web workers, third-party decoders, bundled Natural Earth II base map, sky box,
// widget CSS) from node_modules into public/cesium so the globe is served from this origin and works offline.
// Runs before `dev` and `build`; the copy is git-ignored because it is derived from the pinned `cesium` package.
import { cpSync, existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const source = join(root, "node_modules", "cesium", "Build", "Cesium");
const target = join(root, "public", "cesium");

if (!existsSync(source)) {
  console.error("cesium is not installed; run `npm ci` first.");
  process.exit(1);
}
try {
  rmSync(target, { recursive: true, force: true });
} catch {
  // Windows keeps files open while a dev server runs; overwrite in place instead.
}
mkdirSync(target, { recursive: true });
for (const dir of ["Workers", "ThirdParty", "Assets", "Widgets"]) {
  cpSync(join(source, dir), join(target, dir), { recursive: true });
}
// The prebuilt browser bundle (sets window.Cesium). It is loaded with a script tag at runtime rather than through the app bundler:
// Turbopack's production output of the `cesium` package throws "Octal escape sequences are not allowed in template strings".
// The bundled Knockout library finds the global object with `(0, eval)("this")` while the script loads, which a Content-Security-Policy
// without 'unsafe-eval' blocks, aborting the whole bundle. Kairos keeps that policy strict, so replace that one expression with
// `globalThis` (Apache-2.0 permits modification). The count check fails the build loudly if a Cesium upgrade changes the bundle.
const bundle = readFileSync(join(source, "Cesium.js"), "utf8");
const needle = '(0,eval)("this")';
const occurrences = bundle.split(needle).length - 1;
if (occurrences !== 1) {
  console.error(`Expected exactly one ${needle} in Cesium.js, found ${occurrences}; review the CSP patch in this script.`);
  process.exit(1);
}
writeFileSync(join(target, "Cesium.js"), bundle.replace(needle, "globalThis"));
console.log(`cesium assets copied to ${target}`);
