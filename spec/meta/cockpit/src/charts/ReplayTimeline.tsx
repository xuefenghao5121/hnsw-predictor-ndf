import { useEffect, useRef } from "react";
import * as d3 from "d3";
import type { HopRow } from "../types";

type Props = {
  hops: HopRow[];
  focusedId?: string | null;
  onInspect: (episodeId: string) => void;
};

export function ReplayTimeline({ hops, focusedId, onInspect }: Props) {
  const ref = useRef<SVGSVGElement | null>(null);
  useEffect(() => {
    if (!ref.current || hops.length === 0) return;
    const svg = d3.select(ref.current);
    svg.selectAll("*").remove();
    const width = ref.current?.clientWidth || 720;
    const height = 150;
    const x = d3.scaleLinear().domain([0, Math.max(hops.length - 1, 1)]).range([20, width - 20]);
    const color = d3.scaleOrdinal<string>()
      .domain(["control", "business", "runtime", "canvas"])
      .range(["#7aa2ff", "#8ee0a8", "#e0c36e", "#c9a0ff"]);
    svg.attr("viewBox", `0 0 ${width} ${height}`);
    svg.append("line")
      .attr("x1", 16).attr("x2", width - 16)
      .attr("y1", 70).attr("y2", 70)
      .attr("stroke", "#2c3342");
    const marks = svg.selectAll("g.hop")
      .data(hops)
      .enter()
      .append("g")
      .attr("class", "hop")
      .attr("data-ndf-action", (d) => (d.id === focusedId ? "expand-tech-details" : "inspect-ledger"))
      .attr("transform", (_, i) => `translate(${x(i)},70)`);
    marks.append("circle")
      .attr("r", (d) => (d.id === focusedId ? 8 : 5))
      .attr("fill", (d) => color(d.plane || "control"));
    marks.append("title").text((d) => d.title || d.id);
    marks.filter((d) => d.id !== focusedId).on("click", (_, d) => onInspect(d.id));
  }, [hops, focusedId, onInspect]);
  return <svg className="chart" data-ndf-action="d3-zoom-filter" ref={ref} role="img" aria-label="Replay hop timeline" />;
}
