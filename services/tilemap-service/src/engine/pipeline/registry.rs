//! TMP_003 §4.1 — the modificator registry: dependency graph + Kahn
//! topological sort + single-threaded execution (spec D6).

use std::collections::HashMap;
use std::fmt;
use std::time::{Duration, Instant};

use super::{Modificator, ModificatorContext};

/// Holds the registered modificators + their dependency edges, and runs them in
/// a dependency-respecting topological order.
#[derive(Default)]
pub struct ModificatorRegistry {
    modificators: Vec<Box<dyn Modificator>>,
    /// Extra `(dependent, dependency)` edges from [`Self::dependency`] /
    /// [`Self::postfunction`], beyond each modificator's static
    /// [`Modificator::dependencies`]. Each pair `(x, y)` means "x runs after y".
    extra_edges: Vec<(String, String)>,
}

impl fmt::Debug for ModificatorRegistry {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        let names: Vec<&str> = self.modificators.iter().map(|m| m.name()).collect();
        f.debug_struct("ModificatorRegistry")
            .field("modificators", &names)
            .field("extra_edges", &self.extra_edges)
            .finish()
    }
}

impl ModificatorRegistry {
    pub fn new() -> Self {
        Self::default()
    }

    /// Register a modificator. Names must be unique — a duplicate is rejected at
    /// [`Self::execute`] / topological-sort time.
    pub fn add(&mut self, modificator: Box<dyn Modificator>) {
        self.modificators.push(modificator);
    }

    /// Declare that `modificator` must run **after** `dependency` (§2.1).
    pub fn dependency(&mut self, modificator: &str, dependency: &str) {
        self.extra_edges
            .push((modificator.to_string(), dependency.to_string()));
    }

    /// Declare that `modificator` must run **before** `consumer` — the dual of
    /// [`Self::dependency`] (§2.1).
    pub fn postfunction(&mut self, modificator: &str, consumer: &str) {
        self.extra_edges
            .push((consumer.to_string(), modificator.to_string()));
    }

    /// Number of registered modificators.
    pub fn len(&self) -> usize {
        self.modificators.len()
    }

    /// Whether no modificator is registered.
    pub fn is_empty(&self) -> bool {
        self.modificators.is_empty()
    }

    /// Run every modificator single-threaded in topological order (spec D6).
    /// Errors: [`crate::Error::DependencyCycle`] on a cyclic graph, plus
    /// anything a modificator's `process` returns.
    pub fn execute(&self, ctx: &mut ModificatorContext<'_>) -> crate::Result<()> {
        for i in self.topological_order()? {
            self.modificators[i].process(ctx)?;
        }
        Ok(())
    }

    /// Same as [`Self::execute`] but timestamps each `process` call and
    /// returns the per-modificator wall time in execution order. Used by the
    /// `tilemap-service measure` harness (DEFERRED #029) to narrow the
    /// continent-pipeline cost onto a specific placer. Production callers
    /// should keep using [`Self::execute`] — the `Instant` overhead is
    /// trivial but the `Vec` allocation is not zero.
    pub fn execute_with_timing(
        &self,
        ctx: &mut ModificatorContext<'_>,
    ) -> crate::Result<Vec<(String, Duration)>> {
        let order = self.topological_order()?;
        let mut timings = Vec::with_capacity(order.len());
        for i in order {
            let modificator = &self.modificators[i];
            let t = Instant::now();
            modificator.process(ctx)?;
            timings.push((modificator.name().to_string(), t.elapsed()));
        }
        Ok(timings)
    }

    /// Kahn's algorithm (Kahn 1962) → modificator indices in execution order.
    ///
    /// Edges come from each modificator's [`Modificator::dependencies`] plus the
    /// `extra_edges`; a dependency naming an unregistered modificator is dropped
    /// (treated as already satisfied — spec D7). When several modificators are
    /// ready at once the tie breaks to the lexicographically lower name, so the
    /// order is fully deterministic (spec D6).
    fn topological_order(&self) -> crate::Result<Vec<usize>> {
        let n = self.modificators.len();

        // name → index, rejecting duplicate names.
        let mut name_to_idx: HashMap<&str, usize> = HashMap::with_capacity(n);
        for (i, m) in self.modificators.iter().enumerate() {
            if name_to_idx.insert(m.name(), i).is_some() {
                return Err(crate::Error::Modificator {
                    name: m.name().to_string(),
                    reason: "duplicate modificator name in registry".to_string(),
                });
            }
        }

        // Deduplicated dependency edges as (dependency_idx → dependent_idx).
        let mut edge_set: std::collections::HashSet<(usize, usize)> =
            std::collections::HashSet::new();
        for (dependent, m) in self.modificators.iter().enumerate() {
            for dep_name in m.dependencies() {
                if let Some(&dep) = name_to_idx.get(dep_name) {
                    edge_set.insert((dep, dependent));
                }
            }
        }
        for (dependent_name, dependency_name) in &self.extra_edges {
            if let (Some(&dependent), Some(&dep)) = (
                name_to_idx.get(dependent_name.as_str()),
                name_to_idx.get(dependency_name.as_str()),
            ) {
                edge_set.insert((dep, dependent));
            }
        }

        let mut in_degree = vec![0usize; n];
        let mut successors: Vec<Vec<usize>> = vec![Vec::new(); n];
        for &(dep, dependent) in &edge_set {
            successors[dep].push(dependent);
            in_degree[dependent] += 1;
        }

        // Kahn: repeatedly take the lowest-named modificator with no remaining
        // unsatisfied dependency. `n` is tiny (≤ ~10), so the O(n²) scan is fine.
        let mut processed = vec![false; n];
        let mut order = Vec::with_capacity(n);
        while order.len() < n {
            let mut pick: Option<usize> = None;
            for i in 0..n {
                if processed[i] || in_degree[i] != 0 {
                    continue;
                }
                if pick.is_none_or(|p| self.modificators[i].name() < self.modificators[p].name()) {
                    pick = Some(i);
                }
            }
            match pick {
                Some(i) => {
                    processed[i] = true;
                    order.push(i);
                    for &succ in &successors[i] {
                        in_degree[succ] -= 1;
                    }
                }
                None => {
                    // Nodes remain but none is ready → a dependency cycle.
                    let mut stuck: Vec<&str> = (0..n)
                        .filter(|&i| !processed[i])
                        .map(|i| self.modificators[i].name())
                        .collect();
                    stuck.sort_unstable();
                    return Err(crate::Error::DependencyCycle(stuck.join(", ")));
                }
            }
        }
        Ok(order)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::engine::build_state::TilemapBuildState;
    use crate::seed::TilemapSeed;
    use crate::types::template::{TilemapTemplate, TilemapTemplateId};
    use crate::types::tilemap::GridSize;
    use std::cell::RefCell;
    use std::rc::Rc;

    /// A modificator with static dependencies and a no-op `process`.
    struct TestMod {
        name: &'static str,
        deps: Vec<&'static str>,
    }

    impl Modificator for TestMod {
        fn name(&self) -> &str {
            self.name
        }
        fn dependencies(&self) -> Vec<&str> {
            self.deps.clone()
        }
        fn process(&self, _ctx: &mut ModificatorContext<'_>) -> crate::Result<()> {
            Ok(())
        }
    }

    /// A modificator that records its name into a shared log when run.
    struct LogMod {
        name: &'static str,
        log: Rc<RefCell<Vec<String>>>,
    }

    impl Modificator for LogMod {
        fn name(&self) -> &str {
            self.name
        }
        fn process(&self, _ctx: &mut ModificatorContext<'_>) -> crate::Result<()> {
            self.log.borrow_mut().push(self.name.to_string());
            Ok(())
        }
    }

    fn test_mod(name: &'static str, deps: &[&'static str]) -> Box<dyn Modificator> {
        Box::new(TestMod {
            name,
            deps: deps.to_vec(),
        })
    }

    /// Ordered list of modificator names in the registry's topological order.
    fn order_names(reg: &ModificatorRegistry) -> Vec<&str> {
        reg.topological_order()
            .unwrap()
            .into_iter()
            .map(|i| reg.modificators[i].name())
            .collect()
    }

    #[test]
    fn independent_modificators_order_by_name() {
        let mut reg = ModificatorRegistry::new();
        reg.add(test_mod("charlie", &[]));
        reg.add(test_mod("alpha", &[]));
        reg.add(test_mod("bravo", &[]));
        assert_eq!(order_names(&reg), ["alpha", "bravo", "charlie"]);
    }

    #[test]
    fn static_dependency_orders_before_dependent() {
        // AC-5 — `painter` depends on `placer`, so `placer` runs first.
        let mut reg = ModificatorRegistry::new();
        reg.add(test_mod("painter", &["placer"]));
        reg.add(test_mod("placer", &[]));
        assert_eq!(order_names(&reg), ["placer", "painter"]);
    }

    #[test]
    fn registry_dependency_edge_orders_before_dependent() {
        let mut reg = ModificatorRegistry::new();
        reg.add(test_mod("painter", &[]));
        reg.add(test_mod("placer", &[]));
        reg.dependency("painter", "placer"); // painter after placer
        assert_eq!(order_names(&reg), ["placer", "painter"]);
    }

    #[test]
    fn postfunction_is_the_dual_of_dependency() {
        let mut reg = ModificatorRegistry::new();
        reg.add(test_mod("painter", &[]));
        reg.add(test_mod("placer", &[]));
        reg.postfunction("placer", "painter"); // placer before painter
        assert_eq!(order_names(&reg), ["placer", "painter"]);
    }

    #[test]
    fn unregistered_dependency_is_tolerated() {
        // AC-5 / D7 — TerrainPainter declares deps on modificators that do not
        // exist in Phase 1; the registry must treat them as already satisfied.
        let mut reg = ModificatorRegistry::new();
        reg.add(test_mod("painter", &["town_placer", "water_adopter"]));
        assert_eq!(order_names(&reg), ["painter"]);
    }

    #[test]
    fn dependency_cycle_is_rejected() {
        // AC-5 — a → b → a has no topological order.
        let mut reg = ModificatorRegistry::new();
        reg.add(test_mod("a", &["b"]));
        reg.add(test_mod("b", &["a"]));
        let err = reg.topological_order().unwrap_err();
        assert!(
            matches!(err, crate::Error::DependencyCycle(_)),
            "expected DependencyCycle, got {err:?}",
        );
    }

    #[test]
    fn self_dependency_is_a_cycle() {
        let mut reg = ModificatorRegistry::new();
        reg.add(test_mod("loop", &["loop"]));
        assert!(matches!(
            reg.topological_order().unwrap_err(),
            crate::Error::DependencyCycle(_),
        ));
    }

    #[test]
    fn duplicate_modificator_name_is_rejected() {
        let mut reg = ModificatorRegistry::new();
        reg.add(test_mod("dup", &[]));
        reg.add(test_mod("dup", &[]));
        assert!(matches!(
            reg.topological_order().unwrap_err(),
            crate::Error::Modificator { .. },
        ));
    }

    #[test]
    fn ac1_execute_with_timing_returns_per_modificator_durations_in_execution_order() {
        // AC-1 — DEFERRED #029 instrumentation. `execute_with_timing` must
        // return one `(name, duration)` per modificator, in the same
        // topological execution order as `execute`. Durations are non-zero
        // (each `process` does at least the LogMod push).
        let log: Rc<RefCell<Vec<String>>> = Rc::new(RefCell::new(Vec::new()));
        let mut reg = ModificatorRegistry::new();
        for name in ["a", "b", "c"] {
            reg.add(Box::new(LogMod {
                name,
                log: Rc::clone(&log),
            }));
        }
        reg.dependency("a", "c");
        reg.dependency("b", "c");

        let template = TilemapTemplate {
            template_id: TilemapTemplateId("t".to_string()),
            zones: vec![],
            seed_offset: 0,
        };
        let grid = GridSize { width: 2, height: 2 };
        let mut state = TilemapBuildState::from_zones(vec![], grid);
        let mut ctx = ModificatorContext {
            template: &template,
            grid,
            seed: TilemapSeed(0),
            state: &mut state,
        };
        let timings = reg.execute_with_timing(&mut ctx).unwrap();

        // Same execution order as `execute_runs_modificators_in_topological_order`.
        let names: Vec<&str> = timings.iter().map(|(n, _)| n.as_str()).collect();
        assert_eq!(names, ["c", "a", "b"]);
        // process() ran (the log captured it).
        assert_eq!(*log.borrow(), ["c", "a", "b"]);
        // One entry per modificator.
        assert_eq!(timings.len(), 3);
    }

    #[test]
    fn execute_runs_modificators_in_topological_order() {
        let log: Rc<RefCell<Vec<String>>> = Rc::new(RefCell::new(Vec::new()));
        let mut reg = ModificatorRegistry::new();
        for name in ["a", "b", "c"] {
            reg.add(Box::new(LogMod {
                name,
                log: Rc::clone(&log),
            }));
        }
        // c must run before both a and b; a/b tie-break to the lower name.
        reg.dependency("a", "c");
        reg.dependency("b", "c");

        let template = TilemapTemplate {
            template_id: TilemapTemplateId("t".to_string()),
            zones: vec![],
            seed_offset: 0,
        };
        let grid = GridSize { width: 2, height: 2 };
        let mut state = TilemapBuildState::from_zones(vec![], grid);
        let mut ctx = ModificatorContext {
            template: &template,
            grid,
            seed: TilemapSeed(0),
            state: &mut state,
        };
        reg.execute(&mut ctx).unwrap();
        assert_eq!(*log.borrow(), ["c", "a", "b"]);
    }
}
