export type Vec3 = [number, number, number];
export type Timed = { seconds: number; bag_seconds: number };
export type WrenchSample = Timed & { force: Vec3; torque: Vec3 };
export type Entity<T extends Timed> = {
  id: string; label: string; topic: string; kind: 'wrench'; color: string;
  frame_id?: string; samples: T[]; sample_count: number;
};
export type SpatialData<T extends Timed> = {
  entities: Entity<T>[]; sample_tolerance_seconds: number;
};

// Earlier sample wins an exact tie. Never display outside an entity's lifetime.
export function nearestSample<T extends Timed>(samples: T[], seconds: number, tolerance: number): T | undefined {
  if (!samples.length || seconds < samples[0].seconds || seconds > samples[samples.length-1].seconds) return;
  let low = 0, high = samples.length;
  while (low < high) {
    const mid = (low + high) >>> 1;
    if (samples[mid].seconds < seconds) low = mid + 1; else high = mid;
  }
  const after = samples[Math.min(low, samples.length-1)];
  const before = samples[Math.max(0, low-1)];
  const nearest = seconds - before.seconds <= after.seconds - seconds ? before : after;
  return Math.abs(nearest.seconds-seconds) <= tolerance + 1e-9 ? nearest : undefined;
}

export function boundedSamples<T>(samples: T[], limit: number): T[] {
  if (samples.length <= limit) return samples;
  return Array.from({ length: limit }, (_, i) => samples[Math.round(i*(samples.length-1)/(limit-1))]);
}
