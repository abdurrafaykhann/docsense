/// <reference types="node" />
import { readFileSync } from 'node:fs'
import { expect, test } from 'vitest'

// liquidGL sets pointer-events: none on a glass pane's content layer. Without this override the
// sign-in fields cannot be focused and the navigation links ignore a real mouse (scripted clicks hide
// the problem, because element.click() does not honour pointer-events).
test('glass panes keep their content interactive', () => {
  const css = readFileSync('src/index.css', 'utf8') // vitest runs from the frontend folder
  expect(css).toMatch(/\.ds-glass \.ds-content \*\s*\{[^}]*pointer-events:\s*auto\s*!important/)
})
