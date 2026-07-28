export async function POST(req: Request) {
  const dbUrl = process.env.ATLAS_DB_URL;
  return Response.json({ status: "submitted" });
}
