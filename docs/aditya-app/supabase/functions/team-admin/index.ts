// Aditya Traders: team-admin
// Lets the owner or accountant create logins and reset passwords from inside the app.
// The service key never leaves the server. Every call is checked: the caller must be
// signed in AND be an active owner/accountant (public.is_admin(), same rule as the database).
import { createClient } from "npm:@supabase/supabase-js@2.45.4";

const cors = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};
const reply = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { ...cors, "Content-Type": "application/json" } });

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors });
  if (req.method !== "POST") return reply(405, { error: "POST only." });

  const url = Deno.env.get("SUPABASE_URL")!;
  const anon = Deno.env.get("SUPABASE_ANON_KEY")!;
  const service = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
  const auth = req.headers.get("Authorization") ?? "";
  if (!auth.startsWith("Bearer ")) return reply(401, { error: "Sign in first." });

  // 1. Who is calling? Run is_admin() as the caller, so RLS rules decide.
  const asCaller = createClient(url, anon, { global: { headers: { Authorization: auth } }, auth: { persistSession: false } });
  const { data: who, error: whoErr } = await asCaller.auth.getUser();
  if (whoErr || !who?.user) return reply(401, { error: "Sign in first." });
  const { data: admin, error: admErr } = await asCaller.rpc("is_admin");
  if (admErr || admin !== true) return reply(403, { error: "Only the owner or accountant can manage logins." });

  let b: Record<string, unknown>;
  try { b = await req.json(); } catch { return reply(400, { error: "Bad request." }); }
  const password = String(b.password ?? "");
  if (password.length < 8) return reply(400, { error: "Password must be at least 8 characters." });

  const svc = createClient(url, service, { auth: { persistSession: false } });

  if (b.action === "create") {
    const email = String(b.email ?? "").trim().toLowerCase();
    const role = String(b.role ?? "");
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) return reply(400, { error: "Enter a valid phone number or email." });
    if (!["owner", "accountant", "staff"].includes(role)) return reply(400, { error: "Bad role." });
    const { data, error } = await svc.auth.admin.createUser({ email, password, email_confirm: true });
    if (error) return reply(400, { error: /already|registered|exists/i.test(error.message) ? "A login with this phone/email already exists." : error.message });
    // The database trigger already created the profile (inactive). Approve it with the chosen role.
    const { error: pErr } = await svc.from("profiles").update({
      full_name: String(b.full_name ?? ""), phone: b.phone ? String(b.phone) : null, role, active: true,
    }).eq("id", data.user.id);
    if (pErr) return reply(500, { error: "Login created but profile not updated: " + pErr.message });
    return reply(200, { ok: true, user_id: data.user.id });
  }

  if (b.action === "set_password") {
    const id = String(b.user_id ?? "");
    const { error } = await svc.auth.admin.updateUserById(id, { password });
    if (error) return reply(400, { error: error.message });
    return reply(200, { ok: true });
  }

  return reply(400, { error: "Unknown action." });
});
