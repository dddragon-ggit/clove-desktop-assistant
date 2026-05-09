import "@supabase/functions-js/edge-runtime.d.ts"

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers":
    "authorization, x-client-info, apikey, content-type, x-device-id",
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders })
  }

  try {
    const supabaseUrl = Deno.env.get("SUPABASE_URL")!
    const serviceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!
    const deviceId = req.headers.get("x-device-id") || "unknown"

    const { action, data: payload } = await req.json()

    const headers: Record<string, string> = {
      Authorization: `Bearer ${serviceKey}`,
      "Content-Type": "application/json",
      apikey: serviceKey,
      Prefer: "return=representation",
    }

    let result: Response

    if (action === "select") {
      const url = `${supabaseUrl}/rest/v1/todos?select=*&device_id=eq.${deviceId}&order=created_at.desc`
      result = await fetch(url, { headers })
    } else if (action === "insert") {
      payload.device_id = deviceId
      result = await fetch(`${supabaseUrl}/rest/v1/todos`, {
        method: "POST",
        headers,
        body: JSON.stringify(payload),
      })
    } else if (action === "update") {
      const { id, ...updates } = payload
      updates.device_id = deviceId
      const url = `${supabaseUrl}/rest/v1/todos?id=eq.${id}&device_id=eq.${deviceId}`
      result = await fetch(url, {
        method: "PATCH",
        headers,
        body: JSON.stringify(updates),
      })
    } else if (action === "delete") {
      const url = `${supabaseUrl}/rest/v1/todos?id=eq.${payload.id}&device_id=eq.${deviceId}`
      result = await fetch(url, { method: "DELETE", headers })
    } else {
      return new Response(
        JSON.stringify({ error: "Unknown action" }),
        {
          status: 400,
          headers: { ...corsHeaders, "Content-Type": "application/json" },
        },
      )
    }

    const body = await result.text()
    return new Response(body, {
      status: result.status,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    })
  } catch (error) {
    return new Response(
      JSON.stringify({ error: error.message }),
      {
        status: 500,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      },
    )
  }
})
