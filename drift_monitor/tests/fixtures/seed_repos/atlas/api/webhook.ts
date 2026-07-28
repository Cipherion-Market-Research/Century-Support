// Vercel serverless function (pages/functions style, not app-router)
export default function handler(req, res) {
  const secret = process.env.ATLAS_WEBHOOK_SECRET;
  res.status(200).json({ received: true });
}
