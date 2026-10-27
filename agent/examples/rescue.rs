// Hand-written (27 Oct): serve first a lot that has under 60 minutes before its queue-time limit is breached
// and has not breached it yet; otherwise keep today's pick. On the SMT2020 model, training seeds 100-109:
// queue-time breaches -719 per 3-day window (95% -941 to -496), reward no clear effect. Not scored on the
// held-out seeds.
pub fn key(c: &Cand, _x: &Ctx) -> f64 {
    if c.cqt_slack_minutes < 60.0 && c.cqt_slack_minutes > 0.0 {
        -1.0e6 + c.cqt_slack_minutes
    } else if c.is_default > 0.5 {
        0.0
    } else {
        1.0
    }
}
