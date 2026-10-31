/-
The referee program (docs/LEAN-CHECK.md): `referee FILE` or `referee -` (stdin). It reads the header, then applies
`FabCheck.step` to each event as it is read, and `FabCheck.final` at the `end` line, the same functions `check`
folds. A version 2 receipt's finished lots (`F` lines, after the events) are kept as read and checked at the `end`
line with `FabCheck.finishOne` and `FabCheck.finishCounts`, in the order `checkAll` does (docs/LEAN-FINISH.md). Prints `yes ...`, or `no RULE line N: why`. The read loop and the parser are trusted, not proved.
-/
import FabCheck.Core
open FabCheck

structure Header where
  groups : Nat := 0
  fab : Fab := { toolGroup := #[], routes := #[], lotRoute := #[], lotSize := #[], lotFirst := #[],
                 winFrom := Dy.zero, winTo := Dy.zero }

/-- A line without its trailing newline or spaces. -/
def String.chomp (s : String) : String := s.trimAsciiEnd.toString

def words (l : String) : List String := l.splitOn " "

/-- Read one header line into the header, or say why not. -/
def headerLine (h : Header) (ws : List String) : Except String Header := do
  let nat (w : String) : Except String Nat := match w.toNat? with | some n => pure n | none => throw s!"not a number: {w}"
  let dy (w : String) : Except String Dy := match parseDy w with | some d => pure d | none => throw s!"not a time: {w}"
  let f := h.fab
  match ws with
  | ["run", _sha, _seed, _policy, _until, fr, to] => pure { h with fab := { f with winFrom := ← dy fr, winTo := ← dy to } }
  | ["group", i, _name] =>
    if (← nat i) != h.groups then throw "groups out of order" else pure { h with groups := h.groups + 1 }
  | ["tool", i, g] =>
    if (← nat i) != f.toolGroup.size then throw "tools out of order"
    else if (← nat g) ≥ h.groups then throw "a tool of an unknown group"
    else pure { h with fab := { f with toolGroup := f.toolGroup.push (← nat g) } }
  | ["route", r, _n] =>
    if (← nat r) != f.routes.size then throw "routes out of order"
    else pure { h with fab := { f with routes := f.routes.push #[] } }
  | ["step", r, k, g, b, smp, rw, cto, cl] =>
    let r ← nat r
    if r + 1 != f.routes.size then throw "a step outside its route"
    let route := f.routes[r]!
    if (← nat k) != route.size then throw "steps out of order"
    let g ← nat g
    if g ≥ h.groups then throw "a step of an unknown group"
    let batchMax ← match parseOpt b parseDy with | some x => pure x | none => throw "bad batch maximum"
    let rework ← match parseOpt rw String.toNat? with | some x => pure x | none => throw "bad rework"
    let cqt ← match cto, cl with
      | "-", "-" => pure none
      | a, l => match a.toNat?, parseDy l with
        | some a, some l => pure (some (a, l))
        | _, _ => throw "bad queue-time limit"
    let st : StepInfo := { group := g, batchMax, sampled := smp == "1", rework, cqt }
    pure { h with fab := { f with routes := f.routes.set! r (route.push st) } }
  | ["lot", l, r, size, first] =>
    if (← nat l) != f.lotRoute.size then throw "lots out of order"
    let r ← nat r
    if r ≥ f.routes.size then throw "a lot of an unknown route"
    pure { h with fab := { f with lotRoute := f.lotRoute.push r, lotSize := f.lotSize.push (← nat size),
                                  lotFirst := f.lotFirst.push (← nat first) } }
  | _ => throw "not a header line"

def say (s : String) : IO Unit := do
  let out ← IO.getStdout
  out.putStrLn s
  out.flush

partial def main (args : List String) : IO UInt32 := do
  if args.length != 1 then
    say "usage: referee FILE | referee -"
    return 2
  let input ← match args with
    | ["-"] => IO.getStdin
    | path :: _ => IO.FS.Stream.ofHandle <$> IO.FS.Handle.mk path .read
    | [] => IO.getStdin
  let no (r : Rule) (n : Nat) (why : String) : IO UInt32 := do
    say s!"no {r.name} line {n}: {why}"; return 1
  let first ← input.getLine
  let version : Nat ← match first.chomp with
    | "fabgym-receipt 1" => pure 1
    | "fabgym-receipt 2" => pure 2
    | _ => return ← no .format 1 "not a fabgym-receipt 1 or 2"
  -- the header
  let mut h : Header := {}
  let mut n := 1
  let mut line := ""
  let mut sawRun := false
  repeat
    line ← input.getLine
    n := n + 1
    let ws := words line.chomp
    match ws.head? with
    | some "S" | some "J" | some "F" | some "end" => break
    | _ =>
      if line.isEmpty then break
      if !sawRun && ws.head? != some "run" then return ← no .format n "the run line must come first"
      sawRun := true
      match headerLine h ws with
      | .ok h' => h := h'
      | .error e => return ← no .format n e
  let f := h.fab
  -- the events, each through `step`, then `final` at the end line
  let mut s := init f
  -- a version 2 receipt's finished lots: (lot, time, line), checked at the end line
  let mut fins : Array (Nat × Dy × Nat) := #[]
  repeat
    if line.isEmpty then return ← no .format n "the receipt is cut off before its end line"
    let ws := words line.chomp
    if ws.head? == some "end" then
      let nums := (ws.drop 1).filterMap String.toNat?
      if nums.length != (ws.length - 1) || ws.length != (if version == 1 then 5 else 7) then
        return ← no .format n "bad end line"
      match final s ⟨nums[0]!, nums[1]!, nums[2]!, nums[3]!⟩ with
      | .error e => return ← no e.rule n e.why
      | .ok () => pure ()
      let mut done := ""
      if version == 2 then
        let mut fs := finInit s
        for (lot, t, k) in fins do
          match finishOne f s fs lot t with
          | .ok fs' => fs := fs'
          | .error e => return ← no e.rule k e.why
        match finishCounts fs ⟨nums[4]!, nums[5]!⟩ with
        | .error e => return ← no e.rule n e.why
        | .ok () => pure ()
        done := s!" finished={fs.n} finished_window={fs.nw}"
      let rest ← input.getLine
      if !rest.chomp.isEmpty then return ← no .format (n + 1) "lines after the end line"
      say s!"yes jobs={s.jobs} states={s.states} breaches={s.bTotal} window={s.bWindow}{done}"
      return 0
    if ws.head? == some "F" then
      if version != 2 then return ← no .format n "a finished lot in a version 1 receipt"
      match ws with
      | ["F", l, t] =>
        match l.toNat?, parseDy t with
        | some l, some t => fins := fins.push (l, t, n)
        | _, _ => return ← no .format n "bad finished lot"
      | _ => return ← no .format n "bad finished lot"
      line ← input.getLine
      n := n + 1
      continue
    if !fins.isEmpty then return ← no .format n "an event after the finished lots"
    match parseEvent ws with
    | none => return ← no .format n s!"not an event: {line.chomp}"
    | some ev =>
      match step f s ev with
      | .ok s' => s := s'
      | .error e => return ← no e.rule n e.why
    line ← input.getLine
    n := n + 1
  return 0
