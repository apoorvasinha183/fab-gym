/-
The run referee (docs/LEAN-CHECK.md). Plain Lean 4, no libraries: the receipt's records, exact times, and one pure
`step` that the program applies to each event as it is read. `check` folds the same `step` over a list of events;
`FabCheck/Proofs.lean` proves that `check` succeeding means the five rules hold. Version 2 receipts add the
finished lots; `checkAll` checks them too, rule 6 (docs/LEAN-FINISH.md).
From the SMT2020 testbed; not a real fab.
-/
namespace FabCheck

/-- An exact nonnegative time or limit: `m / 2^e`. -/
structure Dy where
  m : Nat
  e : Nat
deriving Repr, BEq, Inhabited, DecidableEq

/-- Read entry `i` of the referee's memory (the default if out of range). -/
def rd [Inhabited α] (a : Array α) (i : Nat) : α := (a[i]?).getD default

/-- Write entry `i` of the referee's memory (nothing if out of range). -/
def wr (a : Array α) (i : Nat) (v : α) : Array α := a.setIfInBounds i v

namespace Dy
def zero : Dy := ⟨0, 0⟩
/-- `a ≤ b`, exactly. -/
def le (a b : Dy) : Bool := decide (a.m * 2 ^ b.e ≤ b.m * 2 ^ a.e)
/-- `a < b`, exactly. -/
def lt (a b : Dy) : Bool := decide (a.m * 2 ^ b.e < b.m * 2 ^ a.e)
/-- `a + b`, exactly. -/
def add (a b : Dy) : Dy := ⟨a.m * 2 ^ b.e + b.m * 2 ^ a.e, a.e + b.e⟩
def ofNat (n : Nat) : Dy := ⟨n, 0⟩
end Dy

/-- One step of a route. -/
structure StepInfo where
  group : Nat
  /-- the most wafers a job may hold, at a batch step; `none` at any other step -/
  batchMax : Option Dy
  /-- an inspection a lot may skip -/
  sampled : Bool
  /-- the step a lot may be sent back to after this one -/
  rework : Option Nat
  /-- a queue-time limit: the step it runs to, and the minutes -/
  cqt : Option (Nat × Dy)
deriving Repr, Inhabited

/-- What the receipt's header says about the fab and the run. Ids are dense from 0. -/
structure Fab where
  toolGroup : Array Nat
  routes : Array (Array StepInfo)
  lotRoute : Array Nat
  lotSize : Array Nat
  lotFirst : Array Nat
  /-- the scored window (from, to] -/
  winFrom : Dy
  winTo : Dy
deriving Repr, Inhabited

/-- One lot in a job: the lot, its step, when it arrived at the step. -/
structure Entry where
  lot : Nat
  step : Nat
  arrive : Dy
deriving Repr, Inhabited

inductive Event where
  /-- a tool's state changes: 0 working, 1 idle, 2 setup, 3 scheduled down, 4 unscheduled down -/
  | state (tool : Nat) (t : Dy) (code : Nat)
  /-- a job: a tool, its start and end, the lots in it -/
  | job (tool : Nat) (start fin : Dy) (lots : List Entry)
deriving Repr, Inhabited

/-- What the receipt's last line claims. -/
structure Claims where
  jobs : Nat
  states : Nat
  breachesTotal : Nat
  breachesWindow : Nat
deriving Repr, Inhabited

/-- The rule a receipt breaks. -/
inductive Rule where
  | format | oneJob | route | batch | down | breach | finish
deriving Repr, BEq, DecidableEq

def Rule.name : Rule → String
  | .format => "format" | .oneJob => "one-job" | .route => "route"
  | .batch => "batch" | .down => "down" | .breach => "breach" | .finish => "finish"

structure Fault where
  rule : Rule
  why : String

/-! ## What the referee remembers: per tool and per lot, never the jobs themselves -/

structure ToolSt where
  code : Nat := 1
  lastEnd : Dy := Dy.zero
deriving Inhabited

structure LotSt where
  /-- the step of the lot's last job, and that job's end -/
  last : Option (Nat × Dy) := none
  /-- per step that starts a queue-time limit, the latest end of that step -/
  ended : List (Nat × Dy) := []
deriving Inhabited

/-- The steps of a route whose queue-time limit runs to step `to`. -/
def feedersOf (route : Array StepInfo) (to : Nat) : List Nat :=
  (List.range route.size).filter (fun p => match route[p]?.bind (·.cqt) with
    | some (t, _) => t == to
    | none => false)

structure St where
  /-- per route, per step, `feedersOf`, worked out once -/
  feed : Array (Array (List Nat))
  now : Dy
  tools : Array ToolSt
  lots : Array LotSt
  jobs : Nat
  states : Nat
  bTotal : Nat
  bWindow : Nat

def init (f : Fab) : St :=
  { feed := f.routes.map (fun route => (Array.range route.size).map (feedersOf route)),
    now := Dy.zero, tools := Array.replicate f.toolGroup.size {}, lots := Array.replicate f.lotRoute.size {},
    jobs := 0, states := 0, bTotal := 0, bWindow := 0 }

def isDown (code : Nat) : Bool := code == 3 || code == 4

/-- The route's step `k`, if there is one. -/
def stepOf (f : Fab) (lot k : Nat) : Option StepInfo := do
  let r ← f.lotRoute[lot]?
  let route ← f.routes[r]?
  route[k]?

/-- A lot that is about to do step `a` may do step `b` next: `a ≤ b` and every step in `[a, b)` samples. -/
def reach (f : Fab) (lot a b : Nat) : Bool :=
  decide (a ≤ b) && (List.range' a (b - a)).all (fun k => ((stepOf f lot k).map (·.sampled)).getD false)

/-- After step `k`, step `b` may come next: on from `k+1`, or on from where rework sends the lot. -/
def nextOk (f : Fab) (lot k b : Nat) : Bool :=
  reach f lot (k + 1) b || (match (stepOf f lot k).bind (·.rework) with
    | some r => reach f lot r b
    | none => false)

/-- The latest end of step `s` among a lot's remembered ends. -/
def lookupEnd (xs : List (Nat × Dy)) (s : Nat) : Option Dy :=
  (xs.find? (·.1 == s)).map (·.2)

/-- Remember `t` as the latest end of step `s` (newest first, so `lookupEnd` finds it). -/
def setEnd (xs : List (Nat × Dy)) (s : Nat) (t : Dy) : List (Nat × Dy) := (s, t) :: xs

/-- The steps of the lot's route whose limit runs to `step`, from the table worked out once. -/
def feeders (feed : Array (Array (List Nat))) (f : Fab) (lot step : Nat) : List Nat :=
  (((f.lotRoute[lot]?).bind (feed[·]?)).bind (·[step]?)).getD []

/-- How many queue-time limits a lot breaks by beginning `step` at `start`. -/
def lateHere (feed : Array (Array (List Nat))) (f : Fab) (ls : LotSt) (lot step : Nat) (start : Dy) : Nat :=
  (feeders feed f lot step).countP (fun p =>
    match lookupEnd ls.ended p, (stepOf f lot p).bind (·.cqt) with
    | some ep, some (_, lim) => Dy.lt (Dy.add ep lim) start
    | _, _ => false)

def fail (r : Rule) (why : String) : Except Fault α := .error ⟨r, why⟩

def need (b : Bool) (r : Rule) (why : String) : Except Fault Unit :=
  if b then pure () else fail r why

/-- The batch rule for a job's lots (all known lots): one route and step; within the maximum at a batch step, else
one lot. -/
def batchOk (f : Fab) (lots : List Entry) : Bool :=
  match lots with
  | [] => false
  | x :: _ =>
    let r := f.lotRoute[x.lot]?
    let sameStep := lots.all (fun y => y.step == x.step && f.lotRoute[y.lot]? == r)
    let distinct := decide (lots.map (·.lot)).Nodup
    let wafers := (lots.map (fun y => f.lotSize[y.lot]?.getD 0)).sum
    sameStep && distinct &&
      (match (stepOf f x.lot x.step).bind (·.batchMax) with
       | some mx => Dy.le (Dy.ofNat wafers) mx
       | none => lots.length == 1)

/-- The route rule for one lot of a job on `tool` starting at `start`. -/
def routeOk (f : Fab) (ls : LotSt) (tool : Nat) (start : Dy) (x : Entry) : Bool :=
  let groupOk := match stepOf f x.lot x.step, f.toolGroup[tool]? with
    | some st, some g => st.group == g
    | _, _ => false
  let orderOk := match ls.last with
    | none => reach f x.lot (f.lotFirst[x.lot]?.getD 0) x.step
    | some (k, e) => Dy.le e x.arrive && nextOk f x.lot k x.step
  groupOk && Dy.le x.arrive start && orderOk

def inWindow (f : Fab) (t : Dy) : Bool := Dy.lt f.winFrom t && Dy.le t f.winTo

/-- One lot's memory after a job of it that ends at `fin`. -/
def afterJob (f : Fab) (ls : LotSt) (x : Entry) (fin : Dy) : LotSt :=
  { last := some (x.step, fin),
    ended := match (stepOf f x.lot x.step).bind (·.cqt) with
      | some _ => setEnd ls.ended x.step fin
      | none => ls.ended }

/-- Apply one event. -/
def step (f : Fab) (s : St) : Event → Except Fault St
  | .state tool t code => do
    need (tool < s.tools.size) .format s!"unknown tool {tool}"
    need (code ≤ 4) .format s!"unknown state {code}"
    need (Dy.le s.now t) .format "time goes backwards"
    let ts := rd s.tools tool
    need (!isDown code || Dy.le ts.lastEnd t) .down s!"tool {tool} goes down while a job runs on it"
    pure { s with now := t, states := s.states + 1, tools := wr s.tools tool { ts with code := code } }
  | .job tool start fin lots => do
    need (tool < s.tools.size) .format s!"unknown tool {tool}"
    need (Dy.le s.now start) .format "time goes backwards"
    need (lots.all (fun x => x.lot < s.lots.size && (stepOf f x.lot x.step).isSome)) .format "unknown lot or step"
    let ts := rd s.tools tool
    need (Dy.le start fin && Dy.le ts.lastEnd start) .oneJob s!"tool {tool} starts a job before its last job ended"
    need (ts.code == 0) .down s!"tool {tool} is not working when its job starts (state {ts.code})"
    need (batchOk f lots) .batch s!"tool {tool}: the lots break the batch rule"
    need (lots.all (fun x => routeOk f (rd s.lots x.lot) tool start x)) .route s!"tool {tool}: a lot breaks its route"
    let late := (lots.map (fun x => lateHere s.feed f (rd s.lots x.lot) x.lot x.step start)).sum
    let lots' := lots.foldl (fun acc x => wr acc x.lot (afterJob f (rd acc x.lot) x fin)) s.lots
    pure { s with now := start, jobs := s.jobs + 1, lots := lots',
                  tools := wr s.tools tool { ts with lastEnd := fin },
                  bTotal := s.bTotal + late, bWindow := s.bWindow + (if inWindow f start then late else 0) }

/-- The counts at the end must be the receipt's claims. -/
def final (s : St) (c : Claims) : Except Fault Unit := do
  need (s.jobs == c.jobs && s.states == c.states) .format "the counts at the end do not match the receipt"
  need (s.bTotal == c.breachesTotal) .breach s!"breaches: counted {s.bTotal}, claimed {c.breachesTotal}"
  need (s.bWindow == c.breachesWindow) .breach s!"breaches in the window: counted {s.bWindow}, claimed {c.breachesWindow}"

/-- The whole check: every event in order, then the counts. -/
def check (f : Fab) (es : List Event) (c : Claims) : Except Fault Unit := do
  let s ← es.foldlM (step f) (init f)
  final s c

/-! ## Rule 6: a finished lot did every step (docs/LEAN-FINISH.md)

A version 2 receipt lists the finished lots after its events. Each is checked against the memory after every event:
the lot's last job, and so, with rule 2, the whole road it took. -/

/-- What a version 2 receipt's last line adds: the finished lots, in all and in the scored window. -/
structure FinClaims where
  total : Nat
  window : Nat
deriving Repr, Inhabited

/-- How many steps a lot's route has. -/
def routeLen (f : Fab) (lot : Nat) : Nat :=
  (((f.lotRoute[lot]?).bind (f.routes[·]?)).map (·.size)).getD 0

/-- The lot's last job ended by `t`. -/
def endBy (t : Dy) : Option (Nat × Dy) → Bool
  | none => false
  | some (_, e) => Dy.le e t

/-- After the lot's last job, every step left on its route samples, so there is nothing it had to do still. -/
def doneAfter (f : Fab) (lot : Nat) : Option (Nat × Dy) → Bool
  | none => false
  | some (k, _) => reach f lot (k + 1) (routeLen f lot)

/-- The finished lots seen so far, and their counts. -/
structure FinSt where
  seen : Array Bool
  n : Nat
  nw : Nat

def finInit (s : St) : FinSt := { seen := Array.replicate s.lots.size false, n := 0, nw := 0 }

/-- Rule 6 for one finished lot, judged from the memory `s` after every event. -/
def finishOne (f : Fab) (s : St) (fs : FinSt) (lot : Nat) (t : Dy) : Except Fault FinSt := do
  need (lot < s.lots.size) .format s!"unknown lot {lot}"
  need (!(rd fs.seen lot)) .finish s!"lot {lot} is finished twice"
  need (endBy t (rd s.lots lot).last) .finish s!"lot {lot} is finished with no job, or before its last job ends"
  need (doneAfter f lot (rd s.lots lot).last) .finish s!"lot {lot} is finished with a step of its route still to do"
  pure { seen := wr fs.seen lot true, n := fs.n + 1, nw := fs.nw + (if inWindow f t then 1 else 0) }

/-- The finished counts at the end must be the receipt's claims. -/
def finishCounts (fs : FinSt) (c : FinClaims) : Except Fault Unit := do
  need (fs.n == c.total) .finish s!"finished lots: counted {fs.n}, claimed {c.total}"
  need (fs.nw == c.window) .finish s!"finished in the window: counted {fs.nw}, claimed {c.window}"

/-- The whole check of a version 2 receipt: the events and their counts, then every finished lot and theirs. -/
def checkAll (f : Fab) (es : List Event) (c : Claims) (fins : List (Nat × Dy)) (fc : FinClaims) : Except Fault Unit := do
  let s ← es.foldlM (step f) (init f)
  final s c
  let fs ← fins.foldlM (fun fs x => finishOne f s fs x.1 x.2) (finInit s)
  finishCounts fs fc

/-! ## Reading a receipt (trusted, not proved) -/

def parseDy (w : String) : Option Dy :=
  match w.splitOn "/" with
  | [m] => m.toNat?.map (⟨·, 0⟩)
  | [m, e] => do pure ⟨← m.toNat?, ← e.toNat?⟩
  | _ => none

def parseOpt (w : String) (p : String → Option α) : Option (Option α) :=
  if w == "-" then some none else (p w).map some

def parseEntries : List String → Option (List Entry)
  | [] => some []
  | l :: k :: a :: rest => do
    let e : Entry := ⟨← l.toNat?, ← k.toNat?, ← parseDy a⟩
    pure (e :: (← parseEntries rest))
  | _ => none

def parseEvent (ws : List String) : Option Event :=
  match ws with
  | ["S", t, time, c] => do pure (.state (← t.toNat?) (← parseDy time) (← c.toNat?))
  | "J" :: t :: s :: e :: n :: rest => do
    let lots ← parseEntries rest
    if lots.length != (← n.toNat?) then none else pure (.job (← t.toNat?) (← parseDy s) (← parseDy e) lots)
  | _ => none

end FabCheck
