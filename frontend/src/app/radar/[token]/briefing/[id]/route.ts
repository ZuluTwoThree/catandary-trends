import { NextResponse } from "next/server";
import { getCustomerByToken, getBriefingHtml } from "@/lib/radar";

export const dynamic = "force-dynamic";

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ token: string; id: string }> }
) {
  const { token, id } = await params;
  const customer = getCustomerByToken(token);
  if (!customer || customer.status === "cancelled") {
    return new NextResponse("Not found", { status: 404 });
  }
  const briefingId = Number.parseInt(id, 10);
  if (Number.isNaN(briefingId)) {
    return new NextResponse("Not found", { status: 404 });
  }
  const html = getBriefingHtml(customer.id, briefingId);
  if (!html) {
    return new NextResponse("Not found", { status: 404 });
  }
  return new NextResponse(html, {
    headers: {
      "Content-Type": "text/html; charset=utf-8",
      "X-Robots-Tag": "noindex",
      "Cache-Control": "private, no-store",
    },
  });
}
