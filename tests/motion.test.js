import test from 'node:test';
import assert from 'node:assert/strict';
import { MotionGate, difference } from '../study_partner/static/motion.js';
const frame = n => new Uint8Array(64).fill(n);
test('wait for stability, skip unchanged images, respect interval', () => {
  const gate = new MotionGate(0);
  assert.equal(gate.tick(frame(100), 500).analyze, false);
  assert.equal(gate.tick(frame(100), 2500).analyze, true);
  gate.markSent(frame(100), 2500);
  assert.equal(gate.tick(frame(100), 40000).analyze, false);
  assert.equal(gate.tick(frame(150), 40500).moving, true);
  assert.equal(gate.tick(frame(150), 41000).analyze, false);
  assert.equal(gate.tick(frame(150), 43000).analyze, true);
  gate.markSent(frame(150), 43000);
  gate.tick(frame(200), 44000);
  assert.equal(gate.tick(frame(200), 47000).analyze, false);
});
test('nudge cooldown, snooze, and reset do not bombard a child', () => {
  const gate = new MotionGate(0);
  gate.tick(frame(100), 0);
  assert.equal(gate.tick(frame(100), 20000, { idle: 30000 }).nudge, false);
  assert.equal(gate.tick(frame(100), 30000, { idle: 30000 }).nudge, true);
  assert.equal(gate.tick(frame(100), 60000).nudge, true);
  gate.nudge(60000);
  assert.equal(gate.tick(frame(100), 61000).nudge, false);
  gate.snooze(62000);
  assert.equal(gate.tick(frame(100), 150000).nudge, false);
  assert.equal(gate.tick(frame(100), 183000).nudge, true);
  gate.reset(184000);
  assert.equal(gate.tick(frame(100), 184500).nudge, false);
});
test('small noise does not count as writing', () => {
  assert.ok(difference(frame(100), frame(101)) < 0.012);
  const gate = new MotionGate(0); gate.tick(frame(100), 0);
  assert.equal(gate.tick(frame(101), 3000).moving, false);
});
