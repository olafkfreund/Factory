---
layout: default
title: "Guides: using Factory in a team"
permalink: /guides/
---

# Guides

Cross-cutting, turn-by-turn guides for teams running the PARR pipeline. Each one
starts from a user story, gives the exact commands, and states what you should
see at each checkpoint so you can tell a working step from a step that merely
did not error.

Per-service reference lives with each product:
[PFactory]({{ '/pfactory/' | relative_url }}),
[AIFactory]({{ '/aifactory/' | relative_url }}),
[TFactory]({{ '/tfactory/' | relative_url }}),
[CFactory]({{ '/cfactory/' | relative_url }}).

## Start here

| Guide | You want to |
|---|---|
| [Onboarding]({{ '/guides/onboarding/' | relative_url }}) | Get from nothing to a first verified change |
| [Working as a team]({{ '/guides/teams/' | relative_url }}) | Set up roles, approval gates and shared conventions |
| [Boards and work items]({{ '/guides/boards/' | relative_url }}) | Drive work from GitHub, GitLab or Azure DevOps issues |

## Scenario guides

| Guide | Scenario |
|---|---|
| [Cloud development]({{ '/guides/cloud-development/' | relative_url }}) | Build services that target cloud infrastructure |
| [Legacy rewrites]({{ '/guides/legacy-rewrites/' | relative_url }}) | Change code nobody remembers writing |
| [Enterprise scale]({{ '/guides/enterprise-scale/' | relative_url }}) | Many repositories, many contributors, audit obligations |
| [Testing scenarios]({{ '/guides/testing/' | relative_url }}) | Decide what "verified" means and enforce it |

## What these guides promise

They document **what is shipped today**, not what is designed. Where a
capability is planned but not built, it is named as planned with a link to the
RFC, rather than described in the present tense.

That distinction is deliberate. A guide that describes an endpoint which does
not exist costs more than no guide at all: the reader configures against it,
sees nothing work, and cannot tell whether they made a mistake or the feature
did. Two examples from this codebase's own history are documented in
[Testing scenarios]({{ '/guides/testing/' | relative_url }}) because the lesson
generalises.

Every command below has been run against a live fleet. Where output is quoted,
it is real output.

## Conventions used

**Checkpoints.** Each numbered step ends with what you should observe. If you
see something else, stop there rather than continuing — a later step failing for
an earlier reason is the hardest kind of problem to unpick.

**Options tables.** Every flag or environment variable is given with its
options, its default, and what happens when it is unset. "Unset" is a real
configuration, and usually the one you are in when something is not working.

**Nothing is assumed green.** Where a guide tells you to check a gate, it also
tells you how to confirm the gate actually ran, because a check that is skipped
and a check that passed look identical in most user interfaces.
