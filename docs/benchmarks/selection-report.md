# SWE-bench Verified 50-task subset -- selection report

Source: `princeton-nlp/SWE-bench_Verified` (test split, 500 instances, via HF datasets-server rows API).
Selection: seed 42, stratified by repo (proportional largest-remainder over repos with >= 10 instances; smaller repos, 11/500 instances, excluded) then by the dataset's `difficulty` annotation within each repo.

Reproduce:

```
python3 select_tasks.py
```

## Stratification vs. full dataset

### repo

| repo | full (500) | full % | selected (50) | selected % |
|---|---|---|---|---|
| django/django | 231 | 46.2% | 24 | 48.0% |
| sympy/sympy | 75 | 15.0% | 8 | 16.0% |
| sphinx-doc/sphinx | 44 | 8.8% | 5 | 10.0% |
| matplotlib/matplotlib | 34 | 6.8% | 3 | 6.0% |
| scikit-learn/scikit-learn | 32 | 6.4% | 3 | 6.0% |
| astropy/astropy | 22 | 4.4% | 2 | 4.0% |
| pydata/xarray | 22 | 4.4% | 2 | 4.0% |
| pytest-dev/pytest | 19 | 3.8% | 2 | 4.0% |
| pylint-dev/pylint | 10 | 2.0% | 1 | 2.0% |
| psf/requests | 8 | 1.6% | 0 | 0.0% |
| mwaskom/seaborn | 2 | 0.4% | 0 | 0.0% |
| pallets/flask | 1 | 0.2% | 0 | 0.0% |

### difficulty

| difficulty | full (500) | full % | selected (50) | selected % |
|---|---|---|---|---|
| 15 min - 1 hour | 261 | 52.2% | 26 | 52.0% |
| <15 min fix | 194 | 38.8% | 21 | 42.0% |
| 1-4 hours | 42 | 8.4% | 3 | 6.0% |
| >4 hours | 3 | 0.6% | 0 | 0.0% |

## Selected instances

| instance_id | repo | difficulty |
|---|---|---|
| astropy__astropy-14309 | astropy/astropy | <15 min fix |
| astropy__astropy-14598 | astropy/astropy | 15 min - 1 hour |
| django__django-10554 | django/django | 1-4 hours |
| django__django-10999 | django/django | <15 min fix |
| django__django-11149 | django/django | 15 min - 1 hour |
| django__django-11299 | django/django | <15 min fix |
| django__django-11477 | django/django | 15 min - 1 hour |
| django__django-11551 | django/django | 15 min - 1 hour |
| django__django-11749 | django/django | 15 min - 1 hour |
| django__django-12304 | django/django | <15 min fix |
| django__django-12406 | django/django | 15 min - 1 hour |
| django__django-12419 | django/django | <15 min fix |
| django__django-12754 | django/django | 15 min - 1 hour |
| django__django-13023 | django/django | <15 min fix |
| django__django-13344 | django/django | 1-4 hours |
| django__django-13809 | django/django | 15 min - 1 hour |
| django__django-14351 | django/django | 15 min - 1 hour |
| django__django-14771 | django/django | 15 min - 1 hour |
| django__django-15277 | django/django | <15 min fix |
| django__django-15525 | django/django | 15 min - 1 hour |
| django__django-15572 | django/django | <15 min fix |
| django__django-15916 | django/django | 15 min - 1 hour |
| django__django-16100 | django/django | <15 min fix |
| django__django-16429 | django/django | <15 min fix |
| django__django-16950 | django/django | 15 min - 1 hour |
| django__django-9296 | django/django | <15 min fix |
| matplotlib__matplotlib-22719 | matplotlib/matplotlib | <15 min fix |
| matplotlib__matplotlib-24970 | matplotlib/matplotlib | 15 min - 1 hour |
| matplotlib__matplotlib-26342 | matplotlib/matplotlib | 15 min - 1 hour |
| pydata__xarray-4966 | pydata/xarray | 15 min - 1 hour |
| pydata__xarray-6461 | pydata/xarray | <15 min fix |
| pylint-dev__pylint-6386 | pylint-dev/pylint | 15 min - 1 hour |
| pytest-dev__pytest-10051 | pytest-dev/pytest | 15 min - 1 hour |
| pytest-dev__pytest-5809 | pytest-dev/pytest | <15 min fix |
| scikit-learn__scikit-learn-13328 | scikit-learn/scikit-learn | <15 min fix |
| scikit-learn__scikit-learn-14710 | scikit-learn/scikit-learn | 15 min - 1 hour |
| scikit-learn__scikit-learn-25747 | scikit-learn/scikit-learn | 15 min - 1 hour |
| sphinx-doc__sphinx-10449 | sphinx-doc/sphinx | <15 min fix |
| sphinx-doc__sphinx-7440 | sphinx-doc/sphinx | <15 min fix |
| sphinx-doc__sphinx-7748 | sphinx-doc/sphinx | 15 min - 1 hour |
| sphinx-doc__sphinx-7985 | sphinx-doc/sphinx | 15 min - 1 hour |
| sphinx-doc__sphinx-8475 | sphinx-doc/sphinx | <15 min fix |
| sympy__sympy-12481 | sympy/sympy | <15 min fix |
| sympy__sympy-13647 | sympy/sympy | 15 min - 1 hour |
| sympy__sympy-16597 | sympy/sympy | 1-4 hours |
| sympy__sympy-16792 | sympy/sympy | 15 min - 1 hour |
| sympy__sympy-18189 | sympy/sympy | <15 min fix |
| sympy__sympy-19783 | sympy/sympy | 15 min - 1 hour |
| sympy__sympy-23950 | sympy/sympy | 15 min - 1 hour |
| sympy__sympy-24539 | sympy/sympy | <15 min fix |
