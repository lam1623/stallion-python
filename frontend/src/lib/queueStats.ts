import { useMemo } from "react";
import { useStore } from "./store";

export interface QueueProgress {
  /** Share of the work done, weighted by duration (a 2 h film counts more than a clip) */
  percent: number;
  /** Seconds left at the current combined speed, null when nothing is converting */
  eta: number | null;
  total: number;
  completed: number;
  running: number;
}

/** Overall progress of the queue; failed and canceled files do not count. */
export function useQueueProgress(): QueueProgress {
  const jobs = useStore((s) => s.jobs);
  const order = useStore((s) => s.order);

  return useMemo(() => {
    let weight = 0;
    let done = 0;
    let remaining = 0;
    let speed = 0;
    let total = 0;
    let completed = 0;
    let running = 0;
    for (const id of order) {
      const job = jobs[id];
      if (!job || job.status === "canceled" || job.status === "failed") continue;
      const duration = Math.max(job.media.duration_s, 1);
      const percent = job.status === "completed" ? 100 : job.progress.percent;
      total += 1;
      weight += duration;
      done += (duration * percent) / 100;
      if (job.status === "completed") completed += 1;
      else remaining += duration * (1 - percent / 100);
      if (job.status === "running") {
        running += 1;
        if (job.progress.speed) speed += job.progress.speed;
      }
    }
    return {
      percent: weight ? (done / weight) * 100 : 0,
      eta: speed > 0 ? remaining / speed : null,
      total,
      completed,
      running,
    };
  }, [jobs, order]);
}
