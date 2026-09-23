export function difference(a, b) {
  if (!a || !b || a.length !== b.length) return 1;
  let total = 0;
  for (let i = 0; i < a.length; i++) total += Math.abs(a[i] - b[i]);
  return total / (a.length * 255);
}

// Frame motion is a heuristic, not pen tracking or an inference about the child.
export class MotionGate {
  constructor(now = 0) { this.reset(now); }
  reset(now) {
    this.previous = null; this.sent = null; this.lastMotion = now;
    this.lastSent = -Infinity; this.lastNudge = -Infinity; this.snoozeUntil = 0;
  }
  tick(sample, now, { interval = 30000, idle = 30000 } = {}) {
    const moving = this.previous !== null && difference(sample, this.previous) > 0.018;
    if (moving) this.lastMotion = now;
    this.previous = sample.slice();
    const stable = now - this.lastMotion >= 2000;
    return {
      moving, stable,
      analyze: stable && now - this.lastSent >= interval && difference(sample, this.sent) > 0.012,
      nudge: stable && now - this.lastMotion >= idle && now - this.lastNudge >= 60000 && now >= this.snoozeUntil,
      idleSeconds: Math.floor((now - this.lastMotion) / 1000),
    };
  }
  markSent(sample, now) { this.sent = sample.slice(); this.lastSent = now; }
  nudge(now) { this.lastNudge = now; }
  snooze(now) { this.snoozeUntil = now + 120000; this.lastNudge = now; }
}
