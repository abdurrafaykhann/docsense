import { expect, test } from 'vitest'
import { bboxToStyle, pointsToBbox, toneFor } from './bbox'

test('bboxToStyle converts normalised boxes to percentages', () => {
  expect(bboxToStyle([0.1, 0.2, 0.5, 0.3])).toEqual({
    left: '10%',
    top: '20%',
    width: '40%',
    height: '10%',
  })
})

test('pointsToBbox normalises, orders and clamps a drag in any direction', () => {
  const rect = { left: 100, top: 50, width: 200, height: 400 }
  expect(pointsToBbox({ x: 200, y: 250 }, { x: 150, y: 150 }, rect)).toEqual([0.25, 0.25, 0.5, 0.5])
  expect(pointsToBbox({ x: 0, y: 0 }, { x: 999, y: 999 }, rect)).toEqual([0, 0, 1, 1])
})

test('toneFor: reviewed wins, low confidence is bad, flagged is warn', () => {
  expect(toneFor(0.1, ['x'], true)).toBe('reviewed')
  expect(toneFor(0.5, [], false)).toBe('bad')
  expect(toneFor(0.9, ['not_in_ocr'], false)).toBe('warn')
  expect(toneFor(0.95, [], false)).toBe('ok')
})
