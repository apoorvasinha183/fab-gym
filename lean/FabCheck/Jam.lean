/-
The track cannot jam below a count of cars (docs/DOUBLE-CHECK.md, part 2): the counting step, proved.

Pieces of track are stops and stretches; `next a b` says a car on piece `a` may move on to piece `b`. A jam is a set
`S` of full pieces that is closed inside a connected part `C` of the track: from a piece of `S` in `C`, every way on to
a piece of `C` is in `S` too. Why the engine's stuck cars form such a set (a car whose stretch is full takes any other
way out that leads to its target, and inside a connected part every way does) is argued in `crates/fabsim/src/jam.rs`;
here, what follows from it. If such a jam meets the part, it holds the whole part, so the cars on the track are at least
the part's room. Fewer cars than that can never jam.

Checked against Mathlib on the Mac mini. On a teaching fab of our own and the SMT2020 testbed; not a real fab.
-/
import Mathlib

namespace FabCheck.Jam

variable {P : Type}

/-- A jam closed inside a connected part, meeting it, holds all of the part. -/
theorem jam_holds_part (next : P → P → Prop) (C S : Set P)
    (conn : ∀ u ∈ C, ∀ v ∈ C, Relation.ReflTransGen (fun a b => a ∈ C ∧ b ∈ C ∧ next a b) u v)
    (closed : ∀ a b, a ∈ S → a ∈ C → b ∈ C → next a b → b ∈ S)
    (s : P) (hsS : s ∈ S) (hsC : s ∈ C) : C ⊆ S := by
  intro v hv
  have h := conn s hsC v hv
  clear hv
  induction h with
  | refl => exact hsS
  | tail _ hbc ih => exact closed _ _ ih hbc.1 hbc.2.1 hbc.2.2

/-- Full pieces hold their room, so a jam that holds the part puts at least the part's room of cars on the track. -/
theorem cars_at_least [Fintype P] (C S : Finset P) (room cars : P → ℕ)
    (full : ∀ p ∈ S, cars p = room p) (sub : C ⊆ S) : ∑ p ∈ C, room p ≤ ∑ p, cars p := by
  calc ∑ p ∈ C, room p = ∑ p ∈ C, cars p := Finset.sum_congr rfl (fun p hp => (full p (sub hp)).symm)
    _ ≤ ∑ p, cars p := Finset.sum_le_sum_of_subset (Finset.subset_univ C)

/-- The rule the checks apply: with fewer cars on the track than a connected part holds, no jam closed inside that
part can meet it. -/
theorem no_jam_below [Fintype P] [DecidableEq P] (next : P → P → Prop) (C S : Finset P) (room cars : P → ℕ)
    (conn : ∀ u ∈ C, ∀ v ∈ C, Relation.ReflTransGen (fun a b => a ∈ C ∧ b ∈ C ∧ next a b) u v)
    (closed : ∀ a b, a ∈ S → a ∈ C → b ∈ C → next a b → b ∈ S)
    (full : ∀ p ∈ S, cars p = room p)
    (few : ∑ p, cars p < ∑ p ∈ C, room p) : ∀ s ∈ S, s ∉ C := by
  intro s hsS hsC
  have sub : C ⊆ S := by
    intro v hv
    have := jam_holds_part next (C : Set P) (S : Set P) (fun u hu v hv => conn u hu v hv)
      (fun a b ha hac hbc h => closed a b ha hac hbc h) s hsS hsC hv
    exact this
  exact absurd (cars_at_least C S room cars full sub) (not_le.mpr few)

end FabCheck.Jam

#print axioms FabCheck.Jam.jam_holds_part
#print axioms FabCheck.Jam.cars_at_least
#print axioms FabCheck.Jam.no_jam_below
