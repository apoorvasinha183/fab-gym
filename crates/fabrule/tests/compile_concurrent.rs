use std::sync::Barrier;

#[test]
fn concurrent_compilers_publish_complete_modules() {
    let cache = std::env::temp_dir().join(format!("fabgym-compile-review-{}", std::process::id()));
    std::fs::create_dir_all(&cache).unwrap();
    let barrier = Barrier::new(4);
    let results = std::thread::scope(|scope| {
        let jobs: Vec<_> = (0..4).map(|_| scope.spawn(|| {
            barrier.wait();
            fabrule::compile("pub fn key(c: &Cand, _x: &Ctx) -> f64 { c.step + 0.12345 }", &cache)
        })).collect();
        jobs.into_iter().map(|j| j.join().unwrap()).collect::<Vec<_>>()
    });
    let _ = std::fs::remove_dir_all(&cache);
    for result in &results {
        let bytes = result.as_ref().expect("every concurrent compile succeeds");
        assert!(fabrule::Rule::load(bytes).is_ok(), "a complete module is published");
        assert_eq!(bytes, results[0].as_ref().unwrap());
    }
}
