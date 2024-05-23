import React, { useContext } from "react";
import AxesContext from "../AxesProvider";

const StatisticsAnnotation: React.FC = () => {
  const axesContext = useContext(AxesContext);

  // Ensure the context is not null or undefined 
  if (!axesContext) {
    throw new Error("StatisticsAnnotation must be used within an AxesProvider");
  }

  const { axes } = axesContext;

  // Aggregate all blocks from all axes
  const allBlocks = axes.flatMap(axis => axis.blocks);
  const observationPeriod = allBlocks.reduce((total, block) => total + (block.end - block.start), 0);
  const occurrences = new Set(allBlocks.map(block => block.text)).size;
  const frequency = occurrences / observationPeriod;
  const totalDurations = allBlocks.reduce((total, block) => total + (block.end - block.start), 0);
  const averageDuration = totalDurations / occurrences;
  const timeRatio = totalDurations / observationPeriod;
  const sortedBlocks = allBlocks.sort((a, b) => a.start - b.start);
  const latency = sortedBlocks.length > 0 ? sortedBlocks[0].start : 0;

  return (
    <div>
      <h1>Annotation Statistics</h1>
      <ul>
        <li>Occurrences: {occurrences}</li>
        <li>Frequency: {frequency.toFixed(3)}</li>
        <li>Average Duration: {averageDuration.toFixed(2)} seconds</li>
        <li>Time Ratio: {timeRatio.toFixed(3)}</li>
        <li>Latency: {latency} seconds from start</li>
      </ul>
    </div>
  );
};

export default StatisticsAnnotation;
