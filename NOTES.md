# Notes

## Assumptions about the data

I've matched hours to the client's own definition rather than a textbook one: total hours are the sum of clock-out minus clock-in for each shift, a blank clock-out counts as zero, and if clock-out ever comes before clock-in I add 24 hours rather than treating it as an error.I reverse-engineered it from all 2,122 `weekly_summary` rows and it matches exactly. 

A breach is more than 55.0 hours in the week, 45 ordinary plus 10 overtime. I checked the client's own history to be sure the cap is a strict "more than": the largest week that *didn't* breach sits at exactly 10.0 hours of overtime, no more.

Overtime has to be counted per person, not per record. Five people are sitting in the register twice — same ID number, same bank account, same tax number, one record per site — and each record on its own stays just under 45 hours. The BCEA counts overtime per employee, so I merge their hours before running the breach test. Skip that step and the breach simply disappears.

There's no roster in this data. I checked whether I could get away with assuming one — week-to-week schedules don't repeat in any useful way, daily-hours similarity between weeks tops out at 0.83 — so I infer someone's remaining shifts from their own weekday habits instead. That's the single biggest limitation in the model.

Recorded hours understate what actually happened: 184 shifts, about 2.1% of them, are clocked in but never clocked out, and get logged as zero hours. Shift length is capped at 13.5 hours. A no-show leaves no row at all. So wherever I quote an overtime number caused by operational failures, treat it as a floor, not the true figure.

## Checking the note-sorting

I sorted the notes into seven categories: four real reasons for extra hours (client-requested, absence cover, late handover, equipment failure), and three "nothing useful here" buckets (routine, blank, unclassified). I did this with rules, not a model. The notes turned out to be about fifty phrase templates with typos injected and a fixed isiZulu/Afrikaans vocabulary, not free prose, so a deterministic rule set felt like the right tool: I can inspect it, it costs nothing to run, and it re-runs on next week's data without a developer touching it.

I checked it three separate ways.

First, I hand-labelled 180 notes before ever looking at what the classifier said — 100 random plus 80 chosen specifically to hit the rare categories. Against that: 100% category accuracy on the random 100, a kappa of 1.00, zero disagreements across all 180.

Second, I built a completely different classifier — TF-IDF character n-grams with nearest neighbour — and let it vote independently. It agrees with the rules on 95.1% of all 2,117 notes. I read every one of the 104 disagreements myself, and none of them turned out to be a rule error.

Third, I clustered the notes with no labels at all. At seven clusters they group loosely by vocabulary; push the cluster count up toward fifty and each template splits into its own cluster, and each of those maps cleanly onto one category. So the seven-category taxonomy isn't something I imposed from outside, it's really there in the data.

Where I got it wrong: the rules were silently dropping about eleven garbled notes into nothing. The second method is what caught it, so I went back and hardened the typo handling, and `unclassified` is now empty. I want to be honest that this is a limitation dressed up as a win, a genuinely new phrasing now gets forced into the nearest category instead of being flagged as unknown. Worth knowing too: I tuned four of the sub-field rules against the gold set directly, so those particular numbers are a little optimistic. And however good 100% looks, it's 100% for *this* data — fifty templates, one rule apiece — not proof it survives a new supervisor with a different way of writing things up.

Once I attribute each overtime hour to the shift it came from — whenever the weekly total crosses 45 — about 21% of overtime hours carry a note that explains them, and 78% of those turn out to be an operational failure (a no-show, a cover shift, a late handover, broken equipment), not something the client actually asked for. Note coverage overall sits around 24%, so I'd treat that split as a floor too, not the whole picture.

## What a trained model would add, and how I'd test it

**On the notes:** an LLM reads for meaning, so it would generalise to a supervisor who writes "my partner didn't rock up so I held the fort" instead of "relief no show again" — my rules only recognise the fifty-odd sentences that actually show up in this data, nothing else. For a single client with a stable group of supervisors, I still think rules are the right call: every label traces back to a named pattern, and a wrong rule announces itself, where a wrong LLM label looks exactly as confident as a right one. That calculus flips once you're serving many clients — at that point rules as a pre-filter with an LLM handling the residual is probably the better trade.

**On the breach prediction:** I deliberately kept the model small — one pooled slope describing how a person's mid-week pace tends to carry through to the weekend. I tried a 45-feature gradient-boosted classifier against it and it didn't win — with nine weeks of history and 65 breaches total, there just isn't enough signal for something that complex, and the ceiling here isn't really about model choice. About 40% of breaches score under 0.10 on a Wednesday, because the hours that cause them get added between Thursday and Sunday, and nothing in Wednesday's data can see that coming. What's missing is an input, not a better algorithm — the roster. Get that, and the model could also start learning which posts are chronically understaffed and who tends to be the regular cover.

**On testing it properly:** I use an expanding-window backtest — for every past week, pretend it's Wednesday, fit only on the weeks before it, and never let the model see the week it's being scored on. I judge it on PR-AUC and recall, not accuracy, because the base rate is only about 5% and "nobody breaches" would score 95% while being useless. I also check calibration bucket by bucket. And I pull the five split-identity people out of the headline number on purpose, since they lift PR-AUC from 0.24 to 0.43 all on their own — leaving them in would flatter the score. With only 65 breaches total, I'd rather quote the recall/precision trade-off honestly than collapse it into one F1 number. For the notes, the honest version of "testing it" means re-checking against a fresh labelled sample from next week's data, not the same gold set the rules were tuned against.
