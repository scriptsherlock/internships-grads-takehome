# Internship, placement and graduate take home assessment

[job-ad]: https://incident.io/careers#open-roles

## About us

incident.io is the leading AI incident response platform, relied on by some of the best engineering teams in the world when things go wrong.

Since launching in 2021, we've helped over 2,000 companies, including OpenAI, Netflix, and Airbnb, run more than 1 million incidents.

The stakes are real, the talent is insane, and somehow it's a genuinely lovely place to work. We all pull our weight, go the extra mile, and put in the bit of magic most companies don't have time for, all while having fun and never taking ourselves too seriously.

We've raised $96 million from Index Ventures, Insight Partners, and Point Nine, and we're growing fast. There's never been a better time to join.

## What is early careers at incident.io like?

What you need to be successful:
- Have a bias for action and ownership and like to get things shipped, learn from mistakes, and take responsibility for your work.
- Stay curious and don’t just accept things as they are, enjoying asking “why?” and “what if?”
- Collaborate in person and get energy from being around others, bouncing around ideas, asking questions, and giving and receiving feedback.
- Love building whether it’s features, tools, or ideas, and enjoy creating things and seeing them make an impact.
- Enjoy fast-paced environments and feel comfortable with change and the energy that comes with moving quickly.
- Keep a low ego by staying humble and staying focused on the wider mission.

> For more info, check out our [candidate hub](https://incident.io/careers/candidate-hub/early-careers) for a behind-the-scenes look at the life of interns and grads at incident.

## Complete our take-home challenge

### Intro

Imagine you're working at incident.io and we're building a product that can page
(call them, send an SMS, send a notification to a mobile app, etc) engineers
when their services are involved in an incident.

When configuring an on-call system, you don't want to say "whenever service X
goes down, page Y person" as that person probably has a social life and won't
appreciate receiving all the pages, all the time.

Instead, you want to build schedules: a set of people who take it in turns to
provide cover for a service by rotating through on-call shifts.

In JSON form, the configuration that describes how a schedule behaves might look
like this:

```js
// This is a schedule.
{
  "users": [
    "alice",
    "bob",
    "charlie"
  ],

  // 5pm, Friday 6th November 2026
  "handover_start_at": "2026-11-06T17:00:00Z",
  "handover_interval_days": 7
}
```

In that example, our schedule will rotate evenly between those users with the first shift starting at 5pm, 
Friday 6th November 2026, with shift changes happening every 7 days.

That means:

- Alice takes the shift for 1 week, starting at 5pm, Friday 6th November 2026
- Then Bob is on-call for 1 week from 5pm, Friday 13th November 2026
- Then Charlie, then...
- Back to Alice again.

Visually, this might look like this:

![Schedule](./schedule2026.png)

Schedule systems often support 'overrides' where you can add temporary shift
modifications to a schedule, such as if someone wants to go walk their dog or go
to the cinema.

An override specifies the person that will take the shift and the time period it covers.
An example of Charlie covering 5pm–10pm on Monday 9th November 2026 would look like this:

```js
// This is an override.
{
  // Charlie will cover this shift
  "user": "charlie",
  // 5pm, Monday 9th November 2026
  "start_at": "2026-11-09T17:00:00Z",
  // 10pm, Monday 9th November 2026
  "end_at": "2026-11-09T22:00:00Z"
}
```

You can assume that overrides will always be after the schedule's `handover_start_at`, and won't 
overlap with each other.

### Task

We would like you to build – in any language you choose, but ideally one you are
very comfortable in – a script called `./render-schedule` that implements a
scheduling algorithm.

It should be run like so:

```console
$ ./render-schedule \
    --schedule=schedule.json \
    --overrides=overrides.json \
    --from='2026-11-06T17:00:00Z' \
    --until='2026-11-20T17:00:00Z'
[
  {
    "user": "alice",
    "start_at": "2026-11-06T17:00:00Z",
    "end_at": "2026-11-09T17:00:00Z"
  },
  {
    "user": "charlie",
    "start_at": "2026-11-09T17:00:00Z",
    "end_at": "2026-11-09T22:00:00Z"
  },
  {
    "user": "alice",
    "start_at": "2026-11-09T22:00:00Z",
    "end_at": "2026-11-13T17:00:00Z"
  },
  {
    "user": "bob",
    "start_at": "2026-11-13T17:00:00Z",
    "end_at": "2026-11-20T17:00:00Z"
  }
]
```

Where:

- `--schedule` JSON file containing a definition of a schedule (see above example)
- `--overrides` JSON file containing an array of overrides (see above example)
- `--from` the time from which to start listing entries
- `--until` the time until which to list entries

The script should output a JSON array of final schedule as a list of entries.
This should take into account the projected entries (based on the handover
information in the schedule) alongside the provided overrides.

Your schedule should also be truncated based on the from and until parameters provided. 
For example, if an entry was from 1pm November 7 → 1pm November 9, 
but from was 2pm November 8, the entry should be returned as 2pm November 8 → 1pm November 9 
(ignoring the part of the entry that is outside the provided range).

Entries should be truncated to match the from/until parameters.

We care more about correctness than performance: we will only run your code for
time windows up to a few weeks, and with under 100 overrides.

### Code submission and video explanation

We'd like you to submit two things:
1. Your code
2. A 5-minute video walkthrough

Please submit a ZIP file containing the code and a `README.md` that includes 
instructions on running your code, including installation of dependencies.

In the 'notes' field, include a link to a 5-minute video explaining:
- How you approached solving the problem, and why you chose that approach
- How your code implements that solution
- Now you've built the scheduler, what other product features might you build
  on top of this

Imagine you're showing this code to a new team-mate: your video should get
them up-to-speed on the codebase.

(We recommend [Loom](https://www.loom.com) for recording this, but you're welcome 
to use any other tool you're comfortable with).

_You may use AI tools, but you remain responsible for the code you submit. 
You should understand what it does and be able to explain and justify the decisions behind it._
