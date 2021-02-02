Development Guide
=================

Consider any rules here *reasonably soft* and significantly at your discretion.
Do not let a rule prevent you from accomplishing something: work on the
principle that it is easier to ask forgiveness than permission.


Layering
--------

The repository contains two projects that were developed in tandem primarily
due to historical incident. Early development was accelerated by working in one
repository, and while components like ``setup.py`` and the test framework are
presently shared, the ``ansible_mitogen`` and ``mitogen`` packages are still
logically independent.

The ``ansible_mitogen`` package should depend on the ``mitogen`` package,
however the ``mitogen`` package must not depend on the ``ansible_mitogen``
package.


Code Style
----------

Try to conform to house style, but also note there is no precise house style.
Working code trumps all other concerns.

That aside, some general ideas:

* Vaguely PEP-8ish overall
* Black-like use of explicit parenthesis to break up lines and expressions that
  would otherwise wrap
* Typically max 80 column lines. Code that cannot be diffed side-by-side by a
  semi-blind person on a small laptop display without wrapping will likely be
  reformatted
* One import per line, with imports sorted and grouped except where wrapped in
  a control structure
* ``from .. import ..`` for package-internal imports only, use extremely
  sparingly for non-module imports. Unless creating a distinct name for an
  object is explicitly desired, prefer avoiding aliases (``from foo.bar import
  somefunc``) if possible
* Functions generally should try to avoid exceeding 48 lines in length, except
  where there may be good reason to, such as inlining code used in a hot loop
* Try to keep every function documented, and tweak the documentation if a
  change modifies the semantics of the function
* Try to avoid if/else spaghetti in any single function or across a set of functions
* Try to aggressively split out large sub-functions into their own functions
* If adding or removing some public function or class, ensure the ``docs/``
  documentation is updated to match
* Almost all material changes should include a changelog entry


Repository Layout
-----------------

The repository is developed in "traditional Git" style, there is no requirement
for every change to have an associated pull request, except where it is
desirable to trigger GitHub features such as CI or to request review.

It is expected that Git is used as it were designed, as a graph of patches each
having their own permanent identity and ancestry, and that they may flow freely
across branches, in a primarily command-line driven workflow.


Branches
--------

The following branches exist:

* ``master``: development branch for the latest major (0.3 as of writing) series
* ``stable``: release branch for the latest major series
* ``0.2``: development branch for the 0.2 series
* ``0.2-stable``: release branch for the 0.2 series


Commit Messages
---------------

Where possible, prefer to include any associated ticket number in commit
messages, prefixed with ``ticket #123``. For example, instead of:

``fix crash in WidgetClass``

Write:

``ticket #22: fix crash in WidgetClass``

This allows straightforward use of ``git blame`` and ``git log`` to immediately
discover the reason and history behind some change. It also avoids the creating
a dedicated pull request and merge for each small change to track the
relationship between commits and tickets, and allows tagging a ticket after any
PR for it has already been merged.


Commit Descriptions
-------------------

Feel free to use commit message bodies to communicate sundry information about
a change that is not permanent enough to be a comment, but still of historical
value. These bodies are distinctly separate from what may appear in a ticket as
one is user-facing and the other is developer-facing.


Revision History
----------------

Prefer preserving full history of your changes, as this allows precise use of
most Git tooling (particularly ``blame``, ``cherry-pick`` and ``revert``).

Feel free to partially squash away meaningless related changes using ``git
rebase`` prior to merging to another branch such as the main development
branch, but avoid this after the changes have been merged somewhere where they
are or likely will become part of the permanent repository history.


Documentation Branch
--------------------

In order to avoid running CI for documentation changes and tweaks, the
documentation is built from the ``docs-master`` branch. This branch often drifts
away from ``master``, but usually just requires a quick merge to bring things
back to normal.

The documentation branch semantics are that it contains whatever it makes sense
to display on the web. There is no enforced relationship between it and master,
except that whatever it contains should eventually end up back on ``master``.

Automation rebuilds and publishes the ``docs-master`` branch on each commit.

Use your discretion if you decide to bypass CI and commit to ``docs-master``
directly, but if you do, ensure the changes eventually make it back on to
``master``.


Merging to a development branch
-------------------------------

If you can commit directly to the repository, you have been entrusted with the
ability to merge to the development branch at your discretion, so long as tests
are passing and you believe your change to be good.

* Adding extensive new functionality should have some accompanying tests, or
  existing tests augmented to tickle the new functionality

* Request review using a PR from another contributor if you have some doubt
  about a change

Consider requesting review where a change:

* Breaks any interface, either API or user-exposed interface

* Changes compatibility

* Increases dependencies


Release Process
---------------

1. Ensure Changelog is completely up to date with all major changes made since
   the prior release. Use ``git log master..stable`` to determine which commits
   may be missing.
2. Merge any documentations up to ``docs-master`` branch, and verify
   ``docs-master`` is not carrying any changes that are not on ``master``.
2. `Update __init.py__ <https://github.com/dw/mitogen/commit/153d79b878f6be55bcae63b35bf2b21f545820af>`_
3. Create PR for appropriate stable branch and get it reviewed by another maintainer
4. Merge the PR
5. ``git stash``
6. ``git checkout stable``
7. ``git pull``
8. ``git reset --hard origin/stable``
9. ``git tag v0.3.123 -a "Mitogen v0.3.123"`` -- tags must be annotated
10. ``git push --tags``
11. ``python setup.py sdist bdist_wheel``
12. [TBD] https://github.com/mitogen-hq/mitogen/issues/771
13. ``twine upload dist/*.{tar.gz,whl}``

Mailing list:

1. Run ``python scripts/release-notes.py 0.3.123`` and copy its output
2. [TBD]
