# SMT2020 high-volume testbed files

Copied unchanged from the GitHub repository `prosysscience/PySCFabSim-release` at commit `0dbff6a55c30978aa7d61d4cbd42cbf550c48e9a`
(`hvlm/SOURCE_COMMIT`), under that repository's MIT licence (`hvlm/LICENSE`, copyright Research Group
Production Systems).

Cite: D. Kopp, M. Hassoun, A. Kalir and L. Mönch, "SMT2020: A Semiconductor Manufacturing Testbed",
IEEE Transactions on Semiconductor Manufacturing, 2020.

This revision has 105 tool groups, 1,043 tools and routes of 583 and 343 steps. It is a published research
model of a fab; no real fab or real data.

# SMT2020 low-volume/high-mix files (`lvhm/`)

Downloaded 28 Oct 2026 from the same repository and commit (`lvhm/SOURCE_COMMIT`), same MIT licence
(`lvhm/LICENSE`, identical to the repository's). All 20 files match the repository's git blob hashes.

On a first comparison with the high-volume set:
- the same 105 tool groups (plus the `Delay_32` station), with 913 tools against 1,043; 66 groups have different counts;
- ten products; routes 3 and 4 are byte-identical to the high-volume routes;
- routes 1, 2 and 5 to 10 use only tool groups the high-volume fab already has (242 to 529 steps);
- each product is released at about 5.7 lots a day, against about 28.6 a day for each high-volume product.

A published research model of a fab; no real fab or real data.

# The official SMT2020 archive (`../smt2020-official/`, not in git)

Downloaded 28 Oct 2026 from p2schedgen.fernuni-hagen.de (`SMT2020.zip`, 110,359,829 bytes, dated 2 Mar 2023,
SHA-256 19c07bfb68cbc5838429531f27d51428155bb11baf58dc79f8caf84b09856872). The page and the archive state no
licence or terms: kept out of git and used for research until that is clear. It holds all four models in AutoSched
AP format (UTF-16 text) and as Excel workbooks, with documentation:
- dataset 1, high volume: the same revision as `hvlm/` (1,043 tools); differences are trailing blank lines in route 4,
  one lot name (SuperHotLot), one more starting lot (Init_Lot_3_1) and the tool file's layout;
- dataset 2, high mix: compare with `lvhm/` before use;
- dataset 3, high volume with engineering lots: 16,960 engineering lots of 1 to 10 wafers (5.5 on average) on a copy
  of product 3's route with different setups, 20 lots per release on alternating 2- and 5-day gaps (about 31.5
  wafers a day against about 1,393 production wafers a day), priorities 10 and 20; the fab has 1,135 tools (52 groups
  larger) to carry them;
- dataset 4, high mix with engineering lots: three engineering routes; its E_order.txt has 1,048,575 rows (the
  Excel row limit), so it may be truncated; also an alternative order set (`*_high_SL_92PCTL`).
