# Third-party notices

This project reuses source code from third-party repositories only where the upstream license permits it, and
keeps each notice here. The ledger for all 98 manifest repositories is `docs/98_REPOSITORY_INTEGRATION_MASTER_LEDGER.csv`.

## Adapted code

### Interdict: minimum-cost exact cut (adapted)

- Upstream: https://github.com/YashSoni998265/interdict
- Commit: 829f1dd63fab80f56c019c4a0a40d761c822ea2a
- Upstream file and symbols: `backend/src/interdict/engine/planner.py` (`solve`, `_minimal`, `objective`);
  the `Chain` type is from `backend/src/interdict/engine/attackgraph.py`.
- Adapted into: `backend/app/capabilities/adapters/interdict_cut.py` and `backend/app/capabilities/remedy_conflicts.py`
- Local changes: the objective fields were replaced by a caller-supplied cost; strict-mode unknown-impact filtering
  and the deny-all hard-isolation plan were removed; local dataclasses replace Interdict's types; input guards were added.
- Authorship: Yash Soni. Copyright and license as below. The project owner has attested permission from the repository
  owners (USER-ATTESTED, not independently verified). The MIT terms apply to this file on their own, and they require
  the notice below to be kept.

#### License text (copied from the upstream LICENSE file at the commit above)

```
MIT License

Copyright (c) 2026 Yash Soni

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Researched, not copied

The following repositories were read for capability inventory only. No code from them is in the product.

- DevAnuragT/reachable (MIT, Copyright (c) 2026 Anurag Thakur) at commit 8867a6db51ecc8de8471a539575d1b2514340142
- MaybeSomeone-arc18/patchpath (MIT, Copyright (c) 2026 Sanskar Kharya) at commit 6665b03a52bb10b38f4a407951f345de7c98650c

If code from either is adopted later, add its file, commit and the license text here before the code lands.

## Not cleared

63 manifest repositories have no license file. None of their code is in the product. Copying from them requires
a written grant from the owner (not yet linked), and the ledger records that status for each one.
