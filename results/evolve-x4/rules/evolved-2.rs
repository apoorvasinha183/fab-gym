pub fn key(c: &Cand, _x: &Ctx) -> f64 {
    ((60.0_f64).max(1440.0_f64)).max((1.0_f64 * 60.0_f64))
}
