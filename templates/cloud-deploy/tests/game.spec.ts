import { test, expect } from '@playwright/test';

// Plays a full game to a win for TFactoryBot (left column 0,3,6 vs a computer
// that takes the first empty cell), then verifies the scoreboard updates.
test('play tic-tac-toe and verify the scoreboard', async ({ page }) => {
  const base = process.env.TFACTORY_TARGET_URL || 'http://localhost:8080';
  await page.goto(base);
  await page.getByTestId('name').fill('TFactoryBot');
  for (const cell of [0, 3, 6]) {                 // left column
    await page.getByTestId(`cell-${cell}`).click();
  }
  await expect(page.getByTestId('status')).toHaveAttribute('data-result', 'win');
  await expect(page.getByTestId('status')).toContainText('You won');
  // scoreboard reflects the win
  await expect(page.getByTestId('lb-name-0')).toContainText('TFactoryBot', { timeout: 10000 });
});
