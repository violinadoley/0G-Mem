import { NextRequest, NextResponse } from "next/server";

export async function POST(req: NextRequest) {
  const { token, query, variables } = await req.json();

  if (!token) {
    return NextResponse.json({ error: "Missing Railway token" }, { status: 400 });
  }

  const res = await fetch("https://backboard.railway.com/graphql/v2", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ query, variables }),
  });

  const data = await res.json();
  return NextResponse.json(data);
}
