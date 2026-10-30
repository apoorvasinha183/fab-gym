//! The decision as a fab (docs/NARRATIVE.md, deliverable 2). A signed answer, copies of the groups prototypes load
//! most, becomes a variant of today's realistic campus. Today's optimised plan is kept block for block and each copy
//! is placed right after its original, so the plans, the BIM and the bill of materials differ only around the copies.
//! A gigafab-style layout of our own design from the SMT2020 testbed; every placement number is assumed.

use crate::layout::{Block, Config, Plan, Problem};
use crate::pl::{capital, Added, Capital, Place, Sheet};
use crate::shop::Shop;
use crate::twofam::{contested, copy_groups, layout_shop, two_family_shop, EngLots};
use std::collections::HashMap;

/// One copied group: its name in the variant shop (`G@B`), its original and the area both stand in.
#[derive(Clone, Debug, PartialEq)]
pub struct Copied {
    pub copy: String,
    pub original: String,
    pub area: String,
    pub tools: usize,
}

pub struct Variant {
    pub copies: Vec<Copied>,
    /// today's optimised plan with the copies inserted
    pub plan: Plan,
    /// the layout problem over the variant shop (two families, copies included)
    pub problem: Problem,
    /// today's two-family shop plus the copies, with the variant's transport layout
    pub shop: Shop,
    /// hoist metres a day at the variant's two-family flows: today's campus, then the variant's
    travel: (f64, f64),
}

impl Variant {
    /// What the copies cost once and a day after, from the price sheet, standing in the halls.
    pub fn capital(&self, s: &Sheet) -> Capital {
        capital(&Added { tools: self.copies.iter().map(|c| (c.area.clone(), c.tools)).collect(), place: Place::Halls }, s)
    }

    /// Hoist metres a day, today's campus and the variant's, on the same two-family flows. On today's campus the
    /// lots meant for a copy go to its original.
    pub fn travel(&self) -> (f64, f64) {
        self.travel
    }
}

/// Today's plan in another problem's group numbers, with each copy (by its original's name) right after its original.
fn carry(today: &Problem, plan: &Plan, to: &Problem, after: &HashMap<&str, &str>) -> Result<(Plan, usize), String> {
    let index: HashMap<&str, usize> = (0..to.len()).map(|g| (to.name(g), g)).collect();
    let mut placed = 0;
    let mut out = Plan { phases: vec![] };
    for sides in &plan.phases {
        let mut two: [Vec<Block>; 2] = [vec![], vec![]];
        for side in 0..2 {
            for b in &sides[side] {
                let mut groups = vec![];
                for &g in &b.groups {
                    let name = today.name(g);
                    groups.push(*index.get(name).ok_or_else(|| format!("{name} is missing from the variant"))?);
                    if let Some(c) = after.get(name) {
                        groups.push(*index.get(c).ok_or_else(|| format!("{c} is missing from the variant"))?);
                        placed += 1;
                    }
                }
                two[side].push(Block { area: b.area.clone(), groups });
            }
        }
        out.phases.push(two);
    }
    Ok((out, placed))
}

/// The variant for `n` copies (one tool each) of the groups prototypes load most, at prototype scale `share`.
pub fn variant_layout(base: &Shop, areas: &[(String, String)], cfg: &Config, share: f64, n: usize) -> Result<Variant, String> {
    let e = EngLots { scale: share, ..EngLots::published("part_E3", 300.0 * 1440.0, 1) };
    let two = two_family_shop(base, "part_3", &e)?;
    let picks: Vec<(String, usize)> = contested(&two, "B", n).into_iter().map(|g| (g, 1)).collect();
    let mut shop = copy_groups(&two, &picks, "B")?;

    let mut all_areas = areas.to_vec();
    let mut copies = vec![];
    for (g, tools) in &picks {
        let area = areas.iter().find(|x| x.0 == *g).map(|x| x.1.clone()).ok_or_else(|| format!("no area for {g:?}"))?;
        let copy = format!("{g}@B");
        all_areas.push((copy.clone(), area.clone()));
        copies.push(Copied { copy, original: g.clone(), area, tools: *tools });
    }

    // today's plan, exactly as `fabsim layout --real` builds it
    let today = Problem::new(base, areas, cfg)?;
    let todays = today.optimise();

    let problem = Problem::new(&layout_shop(&shop), &all_areas, cfg)?;
    let after: HashMap<&str, &str> = copies.iter().map(|c| (c.original.as_str(), c.copy.as_str())).collect();
    let (plan, placed) = carry(&today, &todays, &problem, &after)?;
    if placed != copies.len() {
        return Err(format!("{placed} of {} copies placed: an original is not in today's plan", copies.len()));
    }
    // today's campus on the same lots: the copies' share of B goes to their originals
    let before_p = Problem::new(&layout_shop(&two), areas, cfg)?;
    let (before_plan, _) = carry(&today, &todays, &before_p, &HashMap::new())?;
    let before = before_p.cost(&before_p.pack(&before_plan));
    let campus = problem.pack(&plan);
    shop.oht = Some(problem.oht(&campus));
    shop.ports = problem.ports(&campus);
    shop.bayrails = problem.bayrails(&campus);
    let travel = (before, problem.cost(&campus));
    Ok(Variant { copies, plan, problem, shop, travel })
}
