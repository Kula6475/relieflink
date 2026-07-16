import { compare } from "bcryptjs";
import { SignJWT, jwtVerify } from "jose";
import { cookies } from "next/headers";

import { sql } from "./db";

const COOKIE_NAME = "relieflink_session";

export type Session = {
  userId: string;
  email: string;
  displayName: string;
  globalRole: "member" | "administrator";
};

function secret() {
  const value = process.env.AUTH_SECRET;
  if (!value || value.length < 32) throw new Error("AUTH_SECRET must be at least 32 characters");
  return new TextEncoder().encode(value);
}

export async function authenticate(email: string, password: string): Promise<Session | null> {
  const rows = await sql()`
    SELECT id, email, display_name, global_role, password_hash
    FROM users WHERE lower(email) = lower(${email}) LIMIT 1
  `;
  const user = rows[0];
  if (!user || !(await compare(password, String(user.password_hash)))) return null;
  return {
    userId: String(user.id),
    email: String(user.email),
    displayName: String(user.display_name),
    globalRole: user.global_role === "administrator" ? "administrator" : "member",
  };
}

export async function setSession(session: Session) {
  const token = await new SignJWT(session)
    .setProtectedHeader({ alg: "HS256" })
    .setIssuedAt()
    .setExpirationTime("12h")
    .sign(secret());
  const store = await cookies();
  store.set(COOKIE_NAME, token, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: 43_200,
  });
}

export async function clearSession() {
  const store = await cookies();
  store.delete(COOKIE_NAME);
}

export async function getSession(): Promise<Session | null> {
  const token = (await cookies()).get(COOKIE_NAME)?.value;
  if (!token) return null;
  try {
    const { payload } = await jwtVerify(token, secret());
    return payload as unknown as Session;
  } catch {
    return null;
  }
}
