import { useEffect, useRef } from "react";
import * as d3 from "d3";
import type { TopicRow } from "../types";

type Props = {
  topics: TopicRow[];
  focusedId?: string | null;
  onOpenWorkbench: (topicId: string) => void;
};

export function TopicOverview({ topics, focusedId, onOpenWorkbench }: Props) {
  const ref = useRef<SVGSVGElement | null>(null);
  useEffect(() => {
    const svg = d3.select(ref.current);
    svg.selectAll("*").remove();
    const width = ref.current?.clientWidth || 640;
    const height = 140;
    const x = d3.scalePoint<string>()
      .domain(topics.map((item) => item.id))
      .range([24, width - 24])
      .padding(0.5);
    const color = d3.scaleOrdinal<string>()
      .domain(["exploring", "blocked", "closing", "promoted", "rejected"])
      .range(["#7aa2ff", "#ff8a8a", "#e0c36e", "#8ee0a8", "#9aa6b8"]);
    svg.attr("viewBox", `0 0 ${width} ${height}`);
    const marks = svg.selectAll("g.topic")
      .data(topics)
      .enter()
      .append("g")
      .attr("class", "topic")
      .attr("data-ndf-action", (d) => (d.id === focusedId ? "tab-topics" : "open-workbench"))
      .attr("transform", (d) => `translate(${x(d.id) || 0},70)`);
    marks.append("circle")
      .attr("r", (d) => (d.id === focusedId ? 10 : 7))
      .attr("fill", (d) => color(d.lifecycle || "exploring"))
      .attr("stroke", "#e8edf5")
      .attr("stroke-width", 0.5);
    marks.append("title").text((d) => `${d.id} ${d.lifecycle || ""}`);
    marks.filter((d) => d.id !== focusedId).on("click", (_, d) => onOpenWorkbench(d.id));
    svg.on("wheel", (event: WheelEvent) => {
      event.preventDefault();
    });
  }, [topics, focusedId, onOpenWorkbench]);
  return <svg className="chart" data-ndf-action="d3-zoom-filter" ref={ref} role="img" aria-label="Topic overview" />;
}
