"""Minimal MLT project Kdenlive and Shotcut can open."""

from __future__ import annotations

from xml.sax.saxutils import escape


def build_mlt(
    *,
    source: str,
    segments: list[tuple[float, float]],
    width: int,
    height: int,
    fps: int,
    title: str,
) -> str:
    entries = []
    for start, end in segments:
        inn = int(round(start * fps))
        out = int(round(end * fps)) - 1
        if out < inn:
            out = inn
        entries.append(f'    <entry producer="source" in="{inn}" out="{out}"/>')
    body = "\n".join(entries)
    safe_source = escape(source, {'"': "&quot;"})
    safe_title = escape(title)
    return f"""<?xml version="1.0" encoding="utf-8"?>
<mlt LC_NUMERIC="C" version="7.28.0" title="{safe_title}" producer="tractor0">
  <profile description="Spool vertical" width="{width}" height="{height}" progressive="1" sample_aspect_num="1" sample_aspect_den="1" display_aspect_num="9" display_aspect_den="16" frame_rate_num="{fps}" frame_rate_den="1" colorspace="709"/>
  <producer id="source">
    <property name="resource">{safe_source}</property>
    <property name="mlt_service">avformat</property>
  </producer>
  <playlist id="playlist0">
    <property name="title">{safe_title}</property>
{body}
  </playlist>
  <tractor id="tractor0" title="{safe_title}">
    <property name="title">{safe_title}</property>
    <track producer="playlist0"/>
  </tractor>
</mlt>
"""
