// Vercel function fronting the abacus indexer for the trading-view widget
export default function handler(req, res) {
  const base = process.env.ABACUS_PUBLIC_BASE;
  res.status(200).json({ base });
}
