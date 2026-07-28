import { NextRequest } from "next/server";

export async function GET(req: NextRequest, { params }: { params: { key: string } }) {
  const base = process.env.ALPHA_METRICS_BASE;
  return Response.json({ key: params.key, base });
}
