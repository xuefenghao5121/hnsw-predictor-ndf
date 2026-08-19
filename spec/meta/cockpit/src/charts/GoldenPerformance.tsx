import { useEffect, useRef } from "react";
import * as d3 from "d3";

type Props = {
  scenes: string[];
  qps: number[];
  recall: string[];
};

export function GoldenPerformance({ scenes, qps, recall }: Props) {
  const ref = useRef<SVGSVGElement | null>(null);
  useEffect(() => {
    if (!ref.current || scenes.length === 0 || qps.length === 0) return;
    const svg = d3.select(ref.current);
    svg.selectAll("*").remove();
    const width = ref.current.clientWidth || 760;
    const height = 220;
    const margin = { top: 18, right: 18, bottom: 58, left: 54 };
    const x = d3.scaleBand()
      .domain(scenes)
      .range([margin.left, width - margin.right])
      .padding(0.24);
    const y = d3.scaleLinear()
      .domain([0, d3.max(qps) || 1])
      .nice()
      .range([height - margin.bottom, margin.top]);
    svg.attr("viewBox", `0 0 ${width} ${height}`);
    svg.append("g")
      .attr("transform", `translate(0,${height - margin.bottom})`)
      .call(d3.axisBottom(x))
      .selectAll("text")
      .attr("transform", "rotate(-18)")
      .style("text-anchor", "end");
    svg.append("g")
      .attr("transform", `translate(${margin.left},0)`)
      .call(d3.axisLeft(y).ticks(5));
    svg.selectAll("rect.golden-qps")
      .data(qps.slice(0, scenes.length))
      .enter()
      .append("rect")
      .attr("class", "golden-qps")
      .attr("x", (_, i) => x(scenes[i]) || 0)
      .attr("y", (d) => y(d))
      .attr("width", x.bandwidth())
      .attr("height", (d) => y(0) - y(d))
      .attr("rx", 4)
      .attr("fill", "#7aa2ff")
      .append("title")
      .text((d, i) => `${scenes[i]} · ${d} QPS · recall ${recall[i] || "—"}`);
    svg.append("text")
      .attr("x", 12)
      .attr("y", 12)
      .attr("fill", "#9aa6b8")
      .attr("font-size", 11)
      .text("QPS");
  }, [scenes, qps, recall]);
  return (
    <svg
      className="chart golden-chart"
      data-ndf-action="d3-zoom-filter"
      ref={ref}
      role="img"
      aria-label="Golden sustained aggregate QPS by memory and thread scene"
    />
  );
}
