import React, { useContext } from "react";
import AxesContext from "../AxesProvider";

const StatisticsTier: React.FC = () => {
  const axesContext = useContext(AxesContext);

  if (!axesContext) {
    throw new Error("StatisticsTier must be used within an AxesProvider");
  }

  const { axes } = axesContext;

  return (
    <div>
      {axes.map((axis, index) => {
        const durations = axis.blocks.map(block => block.end - block.start);
        const totalDurations = durations.reduce((sum, duration) => sum + duration, 0);
        const minDuration = durations.length > 0 ? Math.min(...durations) : 0;
        const maxDuration = durations.length > 0 ? Math.max(...durations) : 0;        
        const avgDuration = totalDurations / durations.length;
        const sortedDurations = durations.slice().sort((a, b) => a - b);
        const medianDuration = sortedDurations.length % 2 === 0 ?
          (sortedDurations[sortedDurations.length / 2 - 1] + sortedDurations[sortedDurations.length / 2]) / 2 :
          sortedDurations[Math.floor(sortedDurations.length / 2)];
          const mediaDuration = axes.reduce((max, axis) => {
            if (axis.blocks.length > 0) {
              const lastBlockEnd = axis.blocks[axis.blocks.length - 1].end;
              return Math.max(max, lastBlockEnd);
            }
            return max;
          }, 0);        
        const annotationDurationPercentage = (totalDurations / mediaDuration) * 100;
        const latency = axis.blocks.length > 0 ? axis.blocks[0].start : 0;

        return (
          <div key={index}>
            <h2>Tier: {axis.axisName || "Unnamed"}</h2>
            <ul>
              <li>Number of Annotations: {durations.length}</li>
              <li>Minimal Duration: {minDuration} seconds</li>
              <li>Maximal Duration: {maxDuration} seconds</li>
              <li>Average Duration: {avgDuration.toFixed(2)} seconds</li>
              <li>Median Duration: {medianDuration} seconds</li>
              <li>Total Annotation Duration: {totalDurations} seconds</li>
              <li>Annotation Duration Percentage: {annotationDurationPercentage.toFixed(2)}%</li>
              <li>Latency: {latency} seconds from start</li>
            </ul>
          </div>
        );
      })}
    </div>
  );
};

export default StatisticsTier;
