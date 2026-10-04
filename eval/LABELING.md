# Building the test set

The test set is what turns "it seems to work" into a number you can publish.
Fifteen contracts are enough for week 1: ten sets of SaaS terms and five data processing agreements.

## Which contracts

Pick vendors you already use or are about to sign with, because those are the contracts you have a real reason to read.
Public terms pages and DPAs are free to download, so save each one as a PDF or HTML file into `eval/contracts/`.
Aim for variety: a few large vendors, a few small ones, at least two that you expect to be bad, and at least one document that is neither type (an NDA or an employment contract) to check that the agent refuses it.

## How to label

Label every contract yourself BEFORE running the agent, otherwise its answer anchors yours.

1. Start a timer.
2. Read the contract against the checklist in `triage/checklists/`.
3. Decide: sign, negotiate or lawyer, using the same rules as the checklist file.
4. Stop the timer and note the minutes in the notes column.
5. Add the row to `manifest.csv`.

The minutes matter. "This took me 22 minutes by hand and the agent 90 seconds plus 4 minutes of my review" is the sentence a CTO remembers.

## What counts as a failure

- The verdict differs from your label. Open the memo, find the item that caused it, and decide who was wrong. Sometimes it will be you, and that is worth a post.
- You labelled it lawyer and the agent said sign. This is the one failure that must be zero.
- A quote in the memo that you cannot find in the contract. The verifier should make this impossible, so treat any case as a bug.

## Running it

    python -m triage.evalrun eval/manifest.csv

The scoreboard is written to `eval/scoreboard.md` and each full result to `eval/results/`.
