---
layout: default
title: RFCs
permalink: /rfc/
---

# RFCs

Statuses are each RFC's own.

{% assign rfc_pages = site.pages | sort: "path" %}
<table>
  <thead><tr><th>RFC</th><th>Status</th></tr></thead>
  <tbody>
  {% for p in rfc_pages %}
    {% assign prefix = p.path | slice: 0, 4 %}
    {% if prefix == "rfc/" and p.name != "index.md" %}
    <tr class="rfc"><td><a href="{{ p.url | relative_url }}">{{ p.title }}</a></td><td>{{ p.status | default: "—" }}</td></tr>
    {% endif %}
  {% endfor %}
  </tbody>
</table>
