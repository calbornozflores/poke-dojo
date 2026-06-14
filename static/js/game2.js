// Game 2 (Guess the Pokédex number) helpers — main flow is in game.html
function clampPokedex(val) {
  return Math.max(1, Math.min(1025, parseInt(val, 10) || 1));
}
