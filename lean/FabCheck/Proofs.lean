/-
The run referee's soundness (docs/LEAN-CHECK.md): when `check` accepts a receipt, the five rules hold for every job
in it. The rules are stated here plainly, over the list of events, with times as rational numbers of minutes; they
use nothing of the referee's memory. Checked against Mathlib on the Mac mini.
From the SMT2020 testbed; not a real fab.
-/
import Mathlib
import FabCheck.Core

namespace FabCheck

/-! ## Exact times as rationals -/

/-- A receipt time as a rational number of minutes. -/
def Dy.toQ (d : Dy) : ℚ := (d.m : ℚ) / 2 ^ d.e

theorem Dy.le_iff (a b : Dy) : Dy.le a b = true ↔ a.toQ ≤ b.toQ := by
  unfold Dy.le Dy.toQ
  rw [decide_eq_true_iff, div_le_div_iff₀ (by positivity) (by positivity)]
  exact_mod_cast Iff.rfl

theorem Dy.lt_iff (a b : Dy) : Dy.lt a b = true ↔ a.toQ < b.toQ := by
  unfold Dy.lt Dy.toQ
  rw [decide_eq_true_iff, div_lt_div_iff₀ (by positivity) (by positivity)]
  exact_mod_cast Iff.rfl

theorem Dy.add_toQ (a b : Dy) : (Dy.add a b).toQ = a.toQ + b.toQ := by
  unfold Dy.add Dy.toQ
  rw [div_add_div _ _ (by positivity) (by positivity)]
  push_cast
  ring

theorem Dy.ofNat_toQ (n : Nat) : (Dy.ofNat n).toQ = n := by
  simp [Dy.ofNat, Dy.toQ]

/-! ## The five rules, stated over the receipt's events -/

/-- When an event happens: a state change's time, or a job's start. -/
def Event.time : Event → Dy
  | .state _ t _ => t
  | .job _ s _ _ => s

/-- The receipt never goes back in time. -/
def TimesInOrder (es : List Event) : Prop :=
  ∀ (i j : Nat) (a b : Event), i ≤ j → es[i]? = some a → es[j]? = some b → a.time.toQ ≤ b.time.toQ

/-- Rule 1. Every job ends no earlier than it starts, and every earlier job on the same tool has ended by the time
it starts: no tool runs two jobs at once. -/
def OneJobAtATime (es : List Event) : Prop :=
  ∀ (i T : Nat) (s e : Dy) (lots : List Entry), es[i]? = some (Event.job T s e lots) →
    s.toQ ≤ e.toQ ∧ ∀ s' e' lots', Event.job T s' e' lots' ∈ es.take i → e'.toQ ≤ s.toQ

/-- A lot about to do step `a` may do step `b` next: `a ≤ b`, and every step in between is an inspection that
samples. -/
def Reach (f : Fab) (lot a b : Nat) : Prop :=
  a ≤ b ∧ ∀ k, a ≤ k → k < b → (stepOf f lot k).map (·.sampled) = some true

/-- After step `k` the lot may go on to step `b`: from `k+1`, or from where rework sends it. -/
def NextStep (f : Fab) (lot k b : Nat) : Prop :=
  Reach f lot (k + 1) b ∨ ∃ r, (stepOf f lot k).bind (·.rework) = some r ∧ Reach f lot r b

/-- The step and end of a lot's last job among `pre`, if it had one. -/
def lastJob (pre : List Event) (l : Nat) : Option (Nat × Dy) :=
  pre.foldl (fun acc e => match e with
    | .job _ _ fin lots => match lots.find? (·.lot == l) with
      | some x => some (x.step, fin)
      | none => acc
    | .state .. => acc) none

/-- Rule 2. Every lot of every job is at a step of the tool's group; it arrived before the job starts; and its step
follows its last job's step by the route (or its listed first step), arriving after that job ended. -/
def FollowsRoutes (f : Fab) (es : List Event) : Prop :=
  ∀ (i T : Nat) (s e : Dy) (lots : List Entry), es[i]? = some (Event.job T s e lots) → ∀ x ∈ lots,
    (stepOf f x.lot x.step).map (·.group) = f.toolGroup[T]? ∧ x.arrive.toQ ≤ s.toQ ∧
    match lastJob (es.take i) x.lot with
    | none => Reach f x.lot (f.lotFirst[x.lot]?.getD 0) x.step
    | some (k, e') => e'.toQ ≤ x.arrive.toQ ∧ NextStep f x.lot k x.step

/-- One job's lots fit: at least one lot, no lot twice, all at one step of one route; at a batch step the wafers are
at most its maximum, at any other step there is exactly one lot. -/
def BatchFits (f : Fab) (lots : List Entry) : Prop :=
  lots ≠ [] ∧ (lots.map (·.lot)).Nodup ∧
  (∀ y ∈ lots, ∀ z ∈ lots, y.step = z.step ∧ f.lotRoute[y.lot]? = f.lotRoute[z.lot]?) ∧
  ∀ y ∈ lots, match (stepOf f y.lot y.step).bind (·.batchMax) with
    | some mx => (((lots.map (fun z => f.lotSize[z.lot]?.getD 0)).sum : ℕ) : ℚ) ≤ mx.toQ
    | none => lots.length = 1

/-- Rule 3. -/
def BatchesFit (f : Fab) (es : List Event) : Prop :=
  ∀ (i T : Nat) (s e : Dy) (lots : List Entry), es[i]? = some (Event.job T s e lots) → BatchFits f lots

/-- A tool's state after the events `pre`: its last state change there, idle (1) if none. -/
def stateAfter (pre : List Event) (T : Nat) : Nat :=
  pre.foldl (fun c e => match e with
    | .state t _ k => if t = T then k else c
    | .job .. => c) 1

/-- Rule 4. A tool is working (state 0) when each of its jobs starts, and when a tool goes down (state 3 or 4),
every earlier job on it has ended. With the times in order, no job overlaps a time its tool is down. -/
def NothingOnDown (es : List Event) : Prop :=
  (∀ (i T : Nat) (s e : Dy) (lots : List Entry), es[i]? = some (Event.job T s e lots) →
    stateAfter (es.take i) T = 0) ∧
  (∀ (k T : Nat) (τ : Dy) (c : Nat), es[k]? = some (Event.state T τ c) → (c = 3 ∨ c = 4) →
    ∀ (s e : Dy) (lots : List Entry), Event.job T s e lots ∈ es.take k → e.toQ ≤ τ.toQ)

/-- The latest end of a job of lot `l` at step `p` among `pre`, if any. -/
def lastEndOf (pre : List Event) (l p : Nat) : Option Dy :=
  pre.foldl (fun acc e => match e with
    | .job _ _ fin lots => if lots.any (fun x => x.lot == l && x.step == p) then some fin else acc
    | .state .. => acc) none

/-- The steps of a lot's route whose queue-time limit runs to `step`. -/
def feedersSpec (f : Fab) (lot step : Nat) : List Nat :=
  (((f.lotRoute[lot]?).bind (f.routes[·]?)).map (feedersOf · step)).getD []

/-- How many limits lot `x` breaks by beginning its step at `start`, after the events `pre`: limits from a step it
ended at `ep`, of `lim` minutes, with `start - ep > lim`. -/
def lateAt (f : Fab) (pre : List Event) (x : Entry) (start : Dy) : Nat :=
  (feedersSpec f x.lot x.step).countP (fun p =>
    match lastEndOf pre x.lot p, (stepOf f x.lot p).bind (·.cqt) with
    | some ep, some (_, lim) => decide (ep.toQ + lim.toQ < start.toQ)
    | _, _ => false)

/-- The breaches an event adds, judged from the events before it. -/
def lateOf (f : Fab) (pre : List Event) : Event → Nat
  | .job _ s _ lots => (lots.map (fun x => lateAt f pre x s)).sum
  | .state .. => 0

/-- All breaches in the receipt. -/
def lateTotal (f : Fab) (es : List Event) : Nat :=
  ((List.range es.length).map (fun i => match es[i]? with
    | some e => lateOf f (es.take i) e
    | none => 0)).sum

def inWindowQ (f : Fab) (t : Dy) : Prop := f.winFrom.toQ < t.toQ ∧ t.toQ ≤ f.winTo.toQ

instance (f : Fab) (t : Dy) : Decidable (inWindowQ f t) := by unfold inWindowQ; infer_instance

/-- The breaches whose late step begins in the window (from, to]. -/
def lateWindow (f : Fab) (es : List Event) : Nat :=
  ((List.range es.length).map (fun i => match es[i]? with
    | some e => if inWindowQ f e.time then lateOf f (es.take i) e else 0
    | none => 0)).sum

/-- Rule 5. The claimed breach counts are the true counts. -/
def BreachesCounted (f : Fab) (es : List Event) (c : Claims) : Prop :=
  c.breachesTotal = lateTotal f es ∧ c.breachesWindow = lateWindow f es

/-! ## What the referee's memory stands for -/

def jobCount (pre : List Event) : Nat := pre.countP (fun e => match e with | .job .. => true | .state .. => false)
def stateCount (pre : List Event) : Nat := pre.countP (fun e => match e with | .job .. => false | .state .. => true)

/-- The referee's memory after the events `pre` says what `pre` says. -/
structure Inv (f : Fab) (pre : List Event) (s : St) : Prop where
  feed : s.feed = (init f).feed
  tsize : s.tools.size = f.toolGroup.size
  lsize : s.lots.size = f.lotRoute.size
  now : ∀ e ∈ pre, e.time.toQ ≤ s.now.toQ
  code : ∀ T, T < s.tools.size → (rd s.tools T).code = stateAfter pre T
  ends : ∀ T s' e' lots, Event.job T s' e' lots ∈ pre → T < s.tools.size ∧ e'.toQ ≤ (rd s.tools T).lastEnd.toQ
  last : ∀ l, l < s.lots.size → (rd s.lots l).last = lastJob pre l
  ended : ∀ l p, l < s.lots.size → ((stepOf f l p).bind (·.cqt)).isSome →
    lookupEnd (rd s.lots l).ended p = lastEndOf pre l p
  jobs : s.jobs = jobCount pre
  states : s.states = stateCount pre
  bt : s.bTotal = lateTotal f pre
  bw : s.bWindow = lateWindow f pre

/-! ## Small facts -/

theorem rd_wr {α} [Inhabited α] (a : Array α) (i j : Nat) (v : α) :
    rd (wr a i v) j = if i = j ∧ i < a.size then v else rd a j := by
  unfold rd wr
  rw [Array.getElem?_setIfInBounds]
  by_cases h1 : i = j
  · subst h1
    by_cases h2 : i < a.size
    · simp [h2]
    · simp [h2, Array.getElem?_eq_none (Nat.le_of_not_lt h2)]
  · simp [h1]

theorem size_wr {α} (a : Array α) (i : Nat) (v : α) : (wr a i v).size = a.size := by
  unfold wr; exact Array.size_setIfInBounds

theorem rd_replicate {α} [Inhabited α] (n i : Nat) (v : α) (h : i < n) : rd (Array.replicate n v) i = v := by
  unfold rd; simp [Array.getElem?_replicate, h]

theorem lookupEnd_setEnd (xs : List (Nat × Dy)) (s q : Nat) (t : Dy) :
    lookupEnd (setEnd xs s t) q = if q = s then some t else lookupEnd xs q := by
  unfold setEnd lookupEnd
  by_cases h : s = q
  · subst h; simp
  · simp [h, Ne.symm h]

theorem Reach_of_reach (f : Fab) (lot a b : Nat) (h : reach f lot a b = true) : Reach f lot a b := by
  unfold reach at h
  rw [Bool.and_eq_true, decide_eq_true_iff, List.all_eq_true] at h
  refine ⟨h.1, fun k hak hkb => ?_⟩
  have hk := h.2 k (by rw [List.mem_range']; exact ⟨k - a, by omega, by omega⟩)
  cases hs : stepOf f lot k <;> simp_all

theorem NextStep_of_nextOk (f : Fab) (lot k b : Nat) (h : nextOk f lot k b = true) : NextStep f lot k b := by
  unfold nextOk at h
  rw [Bool.or_eq_true] at h
  rcases h with h | h
  · exact Or.inl (Reach_of_reach f lot _ _ h)
  · right
    revert h
    cases hr : (stepOf f lot k).bind (·.rework) with
    | none => simp
    | some r => intro h; exact ⟨r, rfl, Reach_of_reach f lot _ _ h⟩

theorem stepOf_eq (f : Fab) (lot r k : Nat) (route : Array StepInfo) (hr : f.lotRoute[lot]? = some r)
    (hro : f.routes[r]? = some route) : stepOf f lot k = route[k]? := by
  simp [stepOf, hr, hro]

/-! ## Reading the checker's steps -/

theorem need_bind {β} (b : Bool) (r : Rule) (w : String) (k : Unit → Except Fault β) (v : β) :
    (need b r w >>= k) = .ok v ↔ b = true ∧ k () = .ok v := by
  unfold need fail
  cases b <;> simp [bind, Except.bind, pure, Except.pure]

theorem pure_ok {α} (x y : α) (h : (pure x : Except Fault α) = .ok y) : y = x := by
  simp only [pure, Except.pure, Except.ok.injEq] at h; exact h.symm

theorem need_ok (b : Bool) (r : Rule) (w : String) : need b r w = .ok () ↔ b = true := by
  unfold need fail
  cases b <;> simp [pure, Except.pure]

theorem final_ok (s : St) (c : Claims) (h : final s c = .ok ()) :
    s.bTotal = c.breachesTotal ∧ s.bWindow = c.breachesWindow := by
  unfold final at h
  simp only [need_bind] at h
  obtain ⟨-, h2, h3⟩ := h
  rw [need_ok] at h3
  simp only [beq_iff_eq] at h2 h3
  exact ⟨h2, h3⟩

theorem step_state (f : Fab) (s s' : St) (T : Nat) (t : Dy) (c : Nat)
    (h : step f s (.state T t c) = .ok s') :
    T < s.tools.size ∧ Dy.le s.now t = true ∧ ((!isDown c) || Dy.le (rd s.tools T).lastEnd t) = true ∧
    s' = { s with now := t, states := s.states + 1, tools := wr s.tools T { rd s.tools T with code := c } } := by
  simp only [step, need_bind, decide_eq_true_eq] at h
  obtain ⟨h1, -, h3, h4, h5⟩ := h
  exact ⟨h1, h3, h4, pure_ok _ _ h5⟩

theorem step_job (f : Fab) (s s' : St) (T : Nat) (st fin : Dy) (lots : List Entry)
    (h : step f s (.job T st fin lots) = .ok s') :
    T < s.tools.size ∧ Dy.le s.now st = true ∧
    (∀ x ∈ lots, x.lot < s.lots.size ∧ (stepOf f x.lot x.step).isSome) ∧
    Dy.le st fin = true ∧ Dy.le (rd s.tools T).lastEnd st = true ∧ (rd s.tools T).code = 0 ∧
    batchOk f lots = true ∧ (∀ x ∈ lots, routeOk f (rd s.lots x.lot) T st x = true) ∧
    s' = { s with now := st, jobs := s.jobs + 1,
                  lots := lots.foldl (fun acc x => wr acc x.lot (afterJob f (rd acc x.lot) x fin)) s.lots,
                  tools := wr s.tools T { rd s.tools T with lastEnd := fin },
                  bTotal := s.bTotal + (lots.map (fun x => lateHere s.feed f (rd s.lots x.lot) x.lot x.step st)).sum,
                  bWindow := s.bWindow + (if inWindow f st then
                    (lots.map (fun x => lateHere s.feed f (rd s.lots x.lot) x.lot x.step st)).sum else 0) } := by
  simp only [step, need_bind, decide_eq_true_eq, Bool.and_eq_true, List.all_eq_true, beq_iff_eq] at h
  obtain ⟨h1, h2, h3, ⟨h4, h5⟩, h6, h7, h8, h9⟩ := h
  refine ⟨h1, h2, fun x hx => ?_, h4, h5, h6, h7, h8, pure_ok _ _ h9⟩
  simpa using h3 x hx

/-! ## The fold, a prefix at a time -/

theorem foldlM_snoc (f : Fab) (pre : List Event) (e : Event) (s' : St)
    (h : (pre ++ [e]).foldlM (step f) (init f) = .ok s') :
    ∃ s, pre.foldlM (step f) (init f) = .ok s ∧ step f s e = .ok s' := by
  rw [List.foldlM_append] at h
  cases hp : pre.foldlM (step f) (init f) with
  | error err => simp [hp, bind, Except.bind] at h
  | ok s =>
    refine ⟨s, rfl, ?_⟩
    simp only [hp, bind, Except.bind, List.foldlM_cons, List.foldlM_nil] at h
    cases hse : step f s e with
    | error err => simp [hse] at h
    | ok v => simp only [hse, pure, Except.pure] at h; rw [h]

theorem foldlM_take (f : Fab) (es : List Event) (s : St) (h : es.foldlM (step f) (init f) = .ok s) (n : Nat) :
    ∃ sn, (es.take n).foldlM (step f) (init f) = .ok sn := by
  rw [← List.take_append_drop n es, List.foldlM_append] at h
  cases hp : (es.take n).foldlM (step f) (init f) with
  | error err => simp [hp, bind, Except.bind] at h
  | ok sn => exact ⟨sn, rfl⟩

/-! ## The memory stays true -/

theorem lastJob_job (pre : List Event) (T : Nat) (s e : Dy) (lots : List Entry) (l : Nat) :
    lastJob (pre ++ [Event.job T s e lots]) l = match lots.find? (·.lot == l) with
      | some x => some (x.step, e)
      | none => lastJob pre l := by
  unfold lastJob; rw [List.foldl_append]; rfl

theorem lastJob_state (pre : List Event) (T : Nat) (t : Dy) (c l : Nat) :
    lastJob (pre ++ [Event.state T t c]) l = lastJob pre l := by
  unfold lastJob; rw [List.foldl_append]; rfl

theorem lastEndOf_job (pre : List Event) (T : Nat) (s e : Dy) (lots : List Entry) (l p : Nat) :
    lastEndOf (pre ++ [Event.job T s e lots]) l p =
      if lots.any (fun x => x.lot == l && x.step == p) then some e else lastEndOf pre l p := by
  unfold lastEndOf; rw [List.foldl_append]; rfl

theorem lastEndOf_state (pre : List Event) (T : Nat) (t : Dy) (c l p : Nat) :
    lastEndOf (pre ++ [Event.state T t c]) l p = lastEndOf pre l p := by
  unfold lastEndOf; rw [List.foldl_append]; rfl

theorem stateAfter_job (pre : List Event) (T : Nat) (s e : Dy) (lots : List Entry) (T' : Nat) :
    stateAfter (pre ++ [Event.job T s e lots]) T' = stateAfter pre T' := by
  unfold stateAfter; rw [List.foldl_append]; rfl

theorem stateAfter_state (pre : List Event) (T : Nat) (t : Dy) (c T' : Nat) :
    stateAfter (pre ++ [Event.state T t c]) T' = if T = T' then c else stateAfter pre T' := by
  unfold stateAfter; rw [List.foldl_append]; rfl

theorem sum_range_snoc (pre : List Event) (e : Event) (g : List Event → Event → Nat) :
    ((List.range (pre ++ [e]).length).map (fun i => match (pre ++ [e])[i]? with
      | some x => g ((pre ++ [e]).take i) x
      | none => 0)).sum =
    ((List.range pre.length).map (fun i => match pre[i]? with
      | some x => g (pre.take i) x
      | none => 0)).sum + g pre e := by
  rw [List.length_append, List.length_singleton, List.range_succ, List.map_append, List.sum_append]
  congr 1
  · apply congrArg
    apply List.map_congr_left
    intro i hi
    rw [List.mem_range] at hi
    rw [List.getElem?_append_left hi, List.take_append_of_le_length (by omega)]
  · simp

theorem lateTotal_snoc (f : Fab) (pre : List Event) (e : Event) :
    lateTotal f (pre ++ [e]) = lateTotal f pre + lateOf f pre e := by
  unfold lateTotal
  exact sum_range_snoc pre e (fun p x => lateOf f p x)

theorem lateWindow_snoc (f : Fab) (pre : List Event) (e : Event) :
    lateWindow f (pre ++ [e]) = lateWindow f pre + (if inWindowQ f e.time then lateOf f pre e else 0) := by
  unfold lateWindow
  exact sum_range_snoc pre e (fun p x => if inWindowQ f x.time then lateOf f p x else 0)

/-- Writing each lot of a job (no lot twice) changes exactly those lots. -/
theorem foldl_set_lots (g : LotSt → Entry → LotSt) (lots : List Entry) (A : Array LotSt)
    (hnd : (lots.map (·.lot)).Nodup) (hin : ∀ x ∈ lots, x.lot < A.size) :
    (lots.foldl (fun acc x => wr acc x.lot (g (rd acc x.lot) x)) A).size = A.size ∧
    ∀ l, rd (lots.foldl (fun acc x => wr acc x.lot (g (rd acc x.lot) x)) A) l =
      match lots.find? (·.lot == l) with
      | some x => g (rd A l) x
      | none => rd A l := by
  induction lots generalizing A with
  | nil => simp
  | cons x xs ih =>
    simp only [List.map_cons, List.nodup_cons] at hnd
    have hx : x.lot < A.size := hin x (by simp)
    have hxs : ∀ y ∈ xs, y.lot < (wr A x.lot (g (rd A x.lot) x)).size := by
      intro y hy; rw [size_wr]; exact hin y (by simp [hy])
    obtain ⟨ihs, ihl⟩ := ih (wr A x.lot (g (rd A x.lot) x)) hnd.2 hxs
    simp only [List.foldl_cons]
    refine ⟨by rw [ihs, size_wr], fun l => ?_⟩
    rw [ihl l]
    by_cases hl : x.lot = l
    · subst hl
      have hnone : xs.find? (·.lot == x.lot) = none := by
        rw [List.find?_eq_none]; intro y hy hyl
        exact hnd.1 (List.mem_map.mpr ⟨y, hy, by simpa using hyl⟩)
      have hfx : (x :: xs).find? (·.lot == x.lot) = some x := by simp
      rw [hnone, hfx]
      dsimp only
      rw [rd_wr, if_pos ⟨rfl, hx⟩]
    · have hfx : (x :: xs).find? (·.lot == l) = xs.find? (·.lot == l) := by simp [hl]
      have hrd : rd (wr A x.lot (g (rd A x.lot) x)) l = rd A l := by
        rw [rd_wr, if_neg (fun h => hl h.1)]
      rw [hfx]
      cases hf : xs.find? (·.lot == l) with
      | none => exact hrd
      | some y => dsimp only; rw [hrd]

theorem inv_init (f : Fab) : Inv f [] (init f) where
  feed := rfl
  tsize := by simp [init]
  lsize := by simp [init]
  now := by simp
  code := by
    intro T h
    simp only [init, Array.size_replicate] at h
    simp only [init]
    rw [rd_replicate _ _ _ h]
    rfl
  ends := by simp
  last := by
    intro l hl
    simp only [init, Array.size_replicate] at hl
    simp only [init]
    rw [rd_replicate _ _ _ hl]
    rfl
  ended := by
    intro l p hl _
    simp only [init, Array.size_replicate] at hl
    simp only [init]
    rw [rd_replicate _ _ _ hl]
    rfl
  jobs := rfl
  states := rfl
  bt := rfl
  bw := rfl

theorem feeders_eq (f : Fab) (lot step : Nat) (hs : (stepOf f lot step).isSome) :
    feeders (init f).feed f lot step = feedersSpec f lot step := by
  unfold feeders feedersSpec init
  cases hr : f.lotRoute[lot]? with
  | none =>
    exfalso
    rw [show stepOf f lot step = none by simp [stepOf, hr]] at hs
    simp at hs
  | some r =>
    cases hro : f.routes[r]? with
    | none => simp [stepOf, hr, hro] at hs
    | some route =>
      rw [stepOf_eq f lot r step route hr hro] at hs
      have hlt : step < route.size := by
        by_contra hc; rw [Array.getElem?_eq_none (by omega)] at hs; simp at hs
      simp [hr, hro, Array.getElem?_map, Array.getElem?_range, hlt]

theorem lateHere_eq (f : Fab) (pre : List Event) (s : St) (hinv : Inv f pre s) (x : Entry) (start : Dy)
    (hl : x.lot < s.lots.size) (hs : (stepOf f x.lot x.step).isSome) :
    lateHere s.feed f (rd s.lots x.lot) x.lot x.step start = lateAt f pre x start := by
  unfold lateHere lateAt
  rw [hinv.feed, feeders_eq f x.lot x.step hs]
  apply List.countP_congr
  intro p hp
  have hq : ((stepOf f x.lot p).bind (·.cqt)).isSome := by
    unfold feedersSpec at hp
    cases hr : f.lotRoute[x.lot]? with
    | none => simp [hr] at hp
    | some r =>
      cases hro : f.routes[r]? with
      | none => simp [hr, hro] at hp
      | some route =>
        rw [stepOf_eq f x.lot r p route hr hro]
        simp only [hr, hro, Option.bind_some, Option.map_some, Option.getD_some, feedersOf, List.mem_filter] at hp
        obtain ⟨_, hp2⟩ := hp
        revert hp2
        cases hc : route[p]?.bind (·.cqt) <;> simp [hc]
  rw [hinv.ended x.lot p hl hq]
  cases he : lastEndOf pre x.lot p <;> cases hc : (stepOf f x.lot p).bind (·.cqt) <;> simp
  rename_i ep c
  rw [Dy.lt_iff, Dy.add_toQ]

theorem inv_step (f : Fab) (pre : List Event) (s s' : St) (e : Event) (hinv : Inv f pre s)
    (h : step f s e = .ok s') : Inv f (pre ++ [e]) s' := by
  cases e with
  | state T t c =>
    obtain ⟨hT, hnow, hdown, rfl⟩ := step_state f s s' T t c h
    exact {
      feed := hinv.feed
      tsize := by rw [size_wr]; exact hinv.tsize
      lsize := hinv.lsize
      now := by
        intro e he
        rcases List.mem_append.mp he with he | he
        · exact le_trans (hinv.now e he) ((Dy.le_iff _ _).mp hnow)
        · rw [List.mem_singleton] at he; subst he; exact le_refl _
      code := by
        intro T' hT'
        rw [size_wr] at hT'
        rw [stateAfter_state, rd_wr]
        by_cases hTT : T = T'
        · subst hTT; rw [if_pos ⟨rfl, hT⟩, if_pos rfl]
        · rw [if_neg (fun h => hTT h.1), if_neg hTT]; exact hinv.code T' hT'
      ends := by
        intro T' s' e' lots hm
        rcases List.mem_append.mp hm with hm | hm
        · obtain ⟨h1, h2⟩ := hinv.ends T' s' e' lots hm
          refine ⟨by rw [size_wr]; exact h1, ?_⟩
          rw [rd_wr]
          by_cases hTT : T = T'
          · subst hTT; rw [if_pos ⟨rfl, hT⟩]; exact h2
          · rw [if_neg (fun h => hTT h.1)]; exact h2
        · rw [List.mem_singleton] at hm; cases hm
      last := by intro l hl; rw [lastJob_state]; exact hinv.last l hl
      ended := by intro l p hl hc; rw [lastEndOf_state]; exact hinv.ended l p hl hc
      jobs := by simp [jobCount, List.countP_append, hinv.jobs]
      states := by simp [stateCount, List.countP_append, hinv.states]
      bt := by rw [lateTotal_snoc]; simp [lateOf, hinv.bt]
      bw := by rw [lateWindow_snoc]; simp [lateOf, hinv.bw] }
  | job T st fin lots =>
    obtain ⟨hT, hnow, hlots, hsf, hle, _, hb, _, rfl⟩ := step_job f s s' T st fin lots h
    have hnd : (lots.map (·.lot)).Nodup := by
      unfold batchOk at hb
      cases lots with
      | nil => simp at hb
      | cons x xs =>
        simp only [Bool.and_eq_true, decide_eq_true_eq] at hb
        exact hb.1.2
    have hin : ∀ x ∈ lots, x.lot < s.lots.size := fun x hx => (hlots x hx).1
    obtain ⟨hsz, hget⟩ := foldl_set_lots (fun ls x => afterJob f ls x fin) lots s.lots hnd hin
    have hlate : (lots.map (fun x => lateHere s.feed f (rd s.lots x.lot) x.lot x.step st)).sum =
        lateOf f pre (Event.job T st fin lots) := by
      unfold lateOf
      congr 1
      apply List.map_congr_left
      intro x hx
      exact lateHere_eq f pre s hinv x st (hlots x hx).1 (hlots x hx).2
    exact {
      feed := hinv.feed
      tsize := by rw [size_wr]; exact hinv.tsize
      lsize := by rw [hsz]; exact hinv.lsize
      now := by
        intro e he
        rcases List.mem_append.mp he with he | he
        · exact le_trans (hinv.now e he) ((Dy.le_iff _ _).mp hnow)
        · rw [List.mem_singleton] at he; subst he; exact le_refl _
      code := by
        intro T' hT'
        rw [size_wr] at hT'
        rw [stateAfter_job, rd_wr]
        by_cases hTT : T = T'
        · subst hTT; rw [if_pos ⟨rfl, hT⟩]; exact hinv.code T hT
        · rw [if_neg (fun h => hTT h.1)]; exact hinv.code T' hT'
      ends := by
        intro T' s' e' lots' hm
        rcases List.mem_append.mp hm with hm | hm
        · obtain ⟨h1, h2⟩ := hinv.ends T' s' e' lots' hm
          refine ⟨by rw [size_wr]; exact h1, ?_⟩
          rw [rd_wr]
          by_cases hTT : T = T'
          · subst hTT; rw [if_pos ⟨rfl, hT⟩]
            exact le_trans h2 (le_trans ((Dy.le_iff _ _).mp hle) ((Dy.le_iff _ _).mp hsf))
          · rw [if_neg (fun h => hTT h.1)]; exact h2
        · rw [List.mem_singleton] at hm
          injection hm with h1 h2 h3 h4
          subst h1; subst h3
          refine ⟨by rw [size_wr]; exact hT, ?_⟩
          rw [rd_wr, if_pos ⟨rfl, hT⟩] <;> exact le_refl _
      last := by
        intro l hl
        rw [hsz] at hl
        rw [hget l, lastJob_job]
        cases hf : lots.find? (·.lot == l) with
        | none => exact hinv.last l hl
        | some x => rfl
      ended := by
        intro l p hl hc
        rw [hsz] at hl
        rw [hget l, lastEndOf_job]
        cases hf : lots.find? (·.lot == l) with
        | none =>
          have hany : lots.any (fun x => x.lot == l && x.step == p) = false := by
            rw [List.any_eq_false]; intro x hx hxl
            simp only [Bool.and_eq_true, beq_iff_eq] at hxl
            rw [List.find?_eq_none] at hf
            exact hf x hx (by simpa using hxl.1)
          rw [hany, if_neg Bool.false_ne_true]
          exact hinv.ended l p hl hc
        | some x =>
          have hxl : x.lot = l := by simpa using List.find?_some hf
          have hxm : x ∈ lots := List.mem_of_find?_eq_some hf
          have huniq : ∀ y ∈ lots, y.lot = l → y = x := fun y hy hyl =>
            List.inj_on_of_nodup_map hnd hy hxm (by rw [hyl, hxl])
          by_cases hxp : x.step = p
          · have hany : lots.any (fun y => y.lot == l && y.step == p) = true :=
              List.any_eq_true.mpr ⟨x, hxm, by simp [hxl, hxp]⟩
            rw [hany, if_pos rfl]
            have hc' : ((stepOf f x.lot x.step).bind (·.cqt)).isSome := by rw [hxl, hxp]; exact hc
            obtain ⟨cq, hcq⟩ := Option.isSome_iff_exists.mp hc'
            show lookupEnd (afterJob f (rd s.lots l) x fin).ended p = some fin
            unfold afterJob
            rw [hcq]
            dsimp only
            rw [lookupEnd_setEnd, if_pos hxp.symm]
          · have hany : lots.any (fun y => y.lot == l && y.step == p) = false := by
              rw [List.any_eq_false]; intro y hy hyl
              simp only [Bool.and_eq_true, beq_iff_eq] at hyl
              have := huniq y hy hyl.1
              subst this
              exact hxp hyl.2
            rw [hany, if_neg Bool.false_ne_true]
            show lookupEnd (afterJob f (rd s.lots l) x fin).ended p = _
            rw [← hinv.ended l p hl hc]
            unfold afterJob
            cases hcq : (stepOf f x.lot x.step).bind (·.cqt) with
            | none => rfl
            | some cq => dsimp only; rw [lookupEnd_setEnd, if_neg (Ne.symm hxp)]
      jobs := by simp [jobCount, List.countP_append, hinv.jobs]
      states := by simp [stateCount, List.countP_append, hinv.states]
      bt := by rw [lateTotal_snoc, hinv.bt, hlate]
      bw := by
        rw [lateWindow_snoc, hinv.bw, hlate]
        congr 1
        have hiff : inWindow f st = true ↔ inWindowQ f st := by
          unfold inWindow inWindowQ; rw [Bool.and_eq_true, Dy.lt_iff, Dy.le_iff]
        by_cases hw : inWindowQ f st
        · have h1 : inWindow f st = true := hiff.mpr hw
          simp only [Event.time, hw, h1, if_true]
        · have h1 : inWindow f st = false := by
            cases h2 : inWindow f st
            · rfl
            · exact absurd (hiff.mp h2) hw
          simp only [Event.time, hw, h1, if_false, Bool.false_eq_true] }

theorem inv_of_ok (f : Fab) (pre : List Event) (s : St) (h : pre.foldlM (step f) (init f) = .ok s) :
    Inv f pre s := by
  induction pre using List.reverseRecOn generalizing s with
  | nil =>
    simp only [List.foldlM_nil, pure, Except.pure, Except.ok.injEq] at h
    subst h; exact inv_init f
  | append_singleton pre e ih =>
    obtain ⟨s0, h0, h1⟩ := foldlM_snoc f pre e s h
    exact inv_step f pre s0 s e (ih s0 h0) h1

/-- At each event, the memory before it says what the events before it say, and the event passes the check. -/
theorem at_event (f : Fab) (es : List Event) (s : St) (h : es.foldlM (step f) (init f) = .ok s)
    (i : Nat) (e : Event) (hi : es[i]? = some e) :
    ∃ si si', Inv f (es.take i) si ∧ step f si e = .ok si' := by
  obtain ⟨sn, hn⟩ := foldlM_take f es s h (i + 1)
  have hte : es.take (i + 1) = es.take i ++ [e] := by rw [List.take_add_one, hi]; rfl
  rw [hte] at hn
  obtain ⟨si, hsi, hstep⟩ := foldlM_snoc f (es.take i) e sn hn
  exact ⟨si, sn, inv_of_ok f _ si hsi, hstep⟩

theorem mem_take_of_lt (es : List Event) (i j : Nat) (a : Event) (hij : i < j) (ha : es[i]? = some a) :
    a ∈ es.take j := by
  rw [List.mem_iff_getElem?]
  exact ⟨i, by rw [List.getElem?_take, if_pos hij, ha]⟩

/-! ## Soundness -/

/-- When the referee accepts a receipt, the times are in order and the five rules hold. -/
theorem check_sound (f : Fab) (es : List Event) (c : Claims) (h : check f es c = .ok ()) :
    TimesInOrder es ∧ OneJobAtATime es ∧ FollowsRoutes f es ∧ BatchesFit f es ∧ NothingOnDown es ∧
      BreachesCounted f es c := by
  unfold check at h
  cases hs : es.foldlM (step f) (init f) with
  | error err => simp [hs, bind, Except.bind] at h
  | ok s =>
    simp only [hs, bind, Except.bind] at h
    refine ⟨?_, ?_, ?_, ?_, ⟨?_, ?_⟩, ?_⟩
    · -- times in order
      intro i j a b hij ha hb
      rcases Nat.lt_or_eq_of_le hij with hlt | heq
      · obtain ⟨sj, sj', hinv, hstep⟩ := at_event f es s hs j b hb
        have hle := hinv.now a (mem_take_of_lt es i j a hlt ha)
        cases b with
        | state T t c => exact le_trans hle ((Dy.le_iff _ _).mp (step_state f sj sj' T t c hstep).2.1)
        | job T st fin lots => exact le_trans hle ((Dy.le_iff _ _).mp (step_job f sj sj' T st fin lots hstep).2.1)
      · subst heq; rw [ha] at hb; cases hb; exact le_refl _
    · -- rule 1
      intro i T st fin lots hi
      obtain ⟨si, si', hinv, hstep⟩ := at_event f es s hs i _ hi
      obtain ⟨-, -, -, hsf, hle, -⟩ := step_job f si si' T st fin lots hstep
      refine ⟨(Dy.le_iff _ _).mp hsf, fun s' e' lots' hm => ?_⟩
      exact le_trans (hinv.ends T s' e' lots' hm).2 ((Dy.le_iff _ _).mp hle)
    · -- rule 2
      intro i T st fin lots hi x hx
      obtain ⟨si, si', hinv, hstep⟩ := at_event f es s hs i _ hi
      obtain ⟨-, -, hlots, -, -, -, -, hr, -⟩ := step_job f si si' T st fin lots hstep
      have hro := hr x hx
      unfold routeOk at hro
      simp only [Bool.and_eq_true] at hro
      obtain ⟨⟨hg, harr⟩, hord⟩ := hro
      refine ⟨?_, (Dy.le_iff _ _).mp harr, ?_⟩
      · revert hg
        cases hst : stepOf f x.lot x.step <;> cases hgT : f.toolGroup[T]? <;> simp_all
      · rw [← hinv.last x.lot (hlots x hx).1]
        revert hord
        cases hl : (rd si.lots x.lot).last with
        | none => intro h; exact Reach_of_reach f _ _ _ h
        | some ke =>
          obtain ⟨k, e'⟩ := ke
          intro h
          simp only [Bool.and_eq_true] at h
          exact ⟨(Dy.le_iff _ _).mp h.1, NextStep_of_nextOk f _ _ _ h.2⟩
    · -- rule 3
      intro i T st fin lots hi
      obtain ⟨si, si', -, hstep⟩ := at_event f es s hs i _ hi
      obtain ⟨-, -, -, -, -, -, hb, -⟩ := step_job f si si' T st fin lots hstep
      unfold batchOk at hb
      cases lots with
      | nil => simp at hb
      | cons x xs =>
        simp only [Bool.and_eq_true, decide_eq_true_eq] at hb
        obtain ⟨⟨hsame, hnd⟩, hmax⟩ := hb
        rw [List.all_eq_true] at hsame
        have hsame' : ∀ y ∈ x :: xs, y.step = x.step ∧ f.lotRoute[y.lot]? = f.lotRoute[x.lot]? := by
          intro y hy; have := hsame y hy; simp only [Bool.and_eq_true, beq_iff_eq] at this; exact this
        refine ⟨by simp, hnd, fun y hy z hz => ?_, fun y hy => ?_⟩
        · obtain ⟨h1, h2⟩ := hsame' y hy; obtain ⟨h3, h4⟩ := hsame' z hz
          exact ⟨h1.trans h3.symm, h2.trans h4.symm⟩
        · obtain ⟨h1, h2⟩ := hsame' y hy
          have hso : stepOf f y.lot y.step = stepOf f x.lot x.step := by
            unfold stepOf; rw [h1, h2]
          rw [hso]
          revert hmax
          cases hbm : (stepOf f x.lot x.step).bind (·.batchMax) with
          | none => simp
          | some mx =>
            intro hm
            have := (Dy.le_iff _ _).mp hm
            rw [Dy.ofNat_toQ] at this
            exact_mod_cast this
    · -- rule 4, jobs start on working tools
      intro i T st fin lots hi
      obtain ⟨si, si', hinv, hstep⟩ := at_event f es s hs i _ hi
      obtain ⟨hT, -, -, -, -, hcode, -⟩ := step_job f si si' T st fin lots hstep
      rw [← hinv.code T hT, hcode]
    · -- rule 4, a tool goes down only after its jobs have ended
      intro k T τ c hk hd st fin lots hm
      obtain ⟨sk, sk', hinv, hstep⟩ := at_event f es s hs k _ hk
      obtain ⟨-, -, hdown, -⟩ := step_state f sk sk' T τ c hstep
      have hisd : isDown c = true := by unfold isDown; rcases hd with rfl | rfl <;> rfl
      rw [hisd, Bool.not_true, Bool.false_or] at hdown
      exact le_trans (hinv.ends T st fin lots hm).2 ((Dy.le_iff _ _).mp hdown)
    · -- rule 5
      have hinv := inv_of_ok f es s hs
      obtain ⟨hbt, hbw⟩ := final_ok s c h
      exact ⟨by rw [← hbt, hinv.bt], by rw [← hbw, hinv.bw]⟩

#print axioms check_sound

end FabCheck
