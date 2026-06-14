// Game 1 (Name the Pokémon) helpers — main flow is in game.html
function normalizeNameGuess(input) {
  return input.trim().toLowerCase().replace(/[^a-z0-9\-]/g, "");
}
