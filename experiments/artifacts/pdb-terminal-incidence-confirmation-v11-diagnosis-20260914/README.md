# V11 infrastructure diagnosis on resumption

The user requested completion of the paper's critical experiments on
2026-09-14. V11 remains unusable for scientific confirmation: its original
all-success condition failed, and no V11 candidate result, translated task,
cohort, or scientific payload is reused.

For infrastructure diagnosis only, the failed campaign's outer stderr files
were inspected. Exactly two report an error: array tasks 205 and 208 both say
`error: translator returned ambiguous exit -9`. No candidate streams or result
files were inspected. This diagnostic inspection occurred after the original
campaign had been declared unusable and is recorded here rather than described
as part of its original outcome-blind source protocol.

The local `sacct` manual distinguishes `JobID`, which reports array jobs as
`ArrayJobID_ArrayTaskID`, from `JobIDRaw`, which reports the internal numeric job
ID. V11 requested the latter while validating the former. A new campaign must
request the actual array identity.

The one retained accounting query in `scheduler.txt` includes CPU use for the
failed jobs and their steps. It is a diagnostic query, not a replacement V11
poll or an authorization to seal V11. Subsequent scheduler queries remain at
least one hour apart.
