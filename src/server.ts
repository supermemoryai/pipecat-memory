/**
 * Simple server for Pipecat + Supermemory Voice Demo
 *
 * The voice pipeline (STT/LLM/TTS) runs on Railway (Python backend).
 * This Cloudflare Worker just serves the frontend and proxies memory APIs.
 */

const SUPERMEMORY_BASE_URL = "https://api.supermemory.ai"

function getApiKey(request: Request, env: Env): string | undefined {
	return request.headers.get("X-Supermemory-Api-Key") || env.SUPERMEMORY_API_KEY
}

function handleApiError(error: any, operation: string): Response {
	console.error(`${operation} error:`, error)
	return Response.json(
		{ error: error.message || `Failed to ${operation.toLowerCase()}` },
		{ status: 500 },
	)
}

// Helper to fetch individual memories from a document
async function fetchDocumentMemories(
	documentId: string,
	apiKey: string,
): Promise<any[]> {
	try {
		const response = await fetch(
			`${SUPERMEMORY_BASE_URL}/v3/documents/${documentId}`,
			{
				method: "GET",
				headers: {
					Authorization: `Bearer ${apiKey}`,
					"Content-Type": "application/json",
				},
			},
		)

		if (!response.ok) {
			console.error(`Failed to fetch document ${documentId}:`, response.status)
			return []
		}

		const data = await response.json()
		return data.memories || []
	} catch (error) {
		console.error(`Error fetching document ${documentId}:`, error)
		return []
	}
}

export default {
	async fetch(request: Request, env: Env, _ctx: ExecutionContext) {
		const url = new URL(request.url)
		const apiKey = getApiKey(request, env)

		// Memories list API - fetches documents and extracts individual memories
		if (url.pathname === "/api/memories" && request.method === "GET") {
			const userId = url.searchParams.get("userId")
			const query = url.searchParams.get("query")

			if (!userId) {
				return Response.json(
					{ error: "userId query parameter is required" },
					{ status: 400 },
				)
			}

			if (!apiKey) {
				return Response.json(
					{ error: "SUPERMEMORY_API_KEY not configured" },
					{ status: 500 },
				)
			}

			try {
				if (query) {
					// Use /v3/search for semantic search when query is provided
					const searchBody = {
						q: query,
						containerTags: [userId],
						limit: 50,
					}

					const response = await fetch(`${SUPERMEMORY_BASE_URL}/v3/search`, {
						method: "POST",
						headers: {
							Authorization: `Bearer ${apiKey}`,
							"Content-Type": "application/json",
						},
						body: JSON.stringify(searchBody),
					})

					if (!response.ok) {
						const errorText = await response.text()
						console.error(
							"Supermemory search API error:",
							response.status,
							errorText,
						)
						return Response.json(
							{ error: `API error: ${response.status}` },
							{ status: response.status },
						)
					}

					const data = await response.json()

					// Return search results
					const memories = (data.results || []).map((item: any) => ({
						id: item.documentId || item.id || `mem-${Math.random()}`,
						memory: item.title || "Untitled memory",
						created_at: item.createdAt || new Date().toISOString(),
						score: item.score,
						type: "search_result",
					}))

					return Response.json({ memories })
				}

				// Step 1: Get list of documents
				const listBody = {
					containerTags: [userId],
					limit: 50,
					sort: "createdAt",
					order: "desc",
				}

				const listResponse = await fetch(
					`${SUPERMEMORY_BASE_URL}/v3/documents/list`,
					{
						method: "POST",
						headers: {
							Authorization: `Bearer ${apiKey}`,
							"Content-Type": "application/json",
						},
						body: JSON.stringify(listBody),
					},
				)

				if (!listResponse.ok) {
					const errorText = await listResponse.text()
					console.error(
						"Supermemory list API error:",
						listResponse.status,
						errorText,
					)
					return Response.json(
						{ error: `API error: ${listResponse.status}` },
						{ status: listResponse.status },
					)
				}

				const listData = await listResponse.json()

				// Parse documents from response
				const rawDocuments =
					listData.memories || listData.documents || listData.results || []

				// Normalize documents
				const documents = rawDocuments.map((item: any) => ({
					id: item.id || item.documentId || `doc-${Math.random()}`,
					title: item.title || "Untitled",
					summary: item.summary || "",
					created_at: item.createdAt || new Date().toISOString(),
					status: item.status || "unknown",
				}))

				// Step 2: Fetch individual memories from all documents
				const allMemories: any[] = []

				for (const doc of documents) {
					const docMemories = await fetchDocumentMemories(doc.id, apiKey)

					// Add all memories from this document
					for (const mem of docMemories) {
						allMemories.push({
							id: mem.id || `mem-${Math.random()}`,
							memory: mem.memory || "",
							documentId: doc.id,
							documentTitle: doc.title,
							created_at: mem.createdAt || doc.created_at,
							type: "extracted_memory",
							version: mem.version,
							sourceCount: mem.sourceCount,
						})
					}
				}

				// Sort memories by created_at (newest first)
				allMemories.sort(
					(a, b) =>
						new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
				)

				return Response.json({ memories: allMemories, documents })
			} catch (error: any) {
				return handleApiError(error, "Memories fetch")
			}
		}

		// Profile API - builds profile from document memories (isStatic field)
		if (url.pathname === "/api/profile" && request.method === "GET") {
			const userId = url.searchParams.get("userId")
			if (!userId || !apiKey) {
				return Response.json(
					{ error: "userId and API key required" },
					{ status: 400 },
				)
			}

			try {
				// Get list of documents for this user
				const listResponse = await fetch(
					`${SUPERMEMORY_BASE_URL}/v3/documents/list`,
					{
						method: "POST",
						headers: {
							Authorization: `Bearer ${apiKey}`,
							"Content-Type": "application/json",
						},
						body: JSON.stringify({
							containerTags: [userId],
							limit: 20,
							sort: "createdAt",
							order: "desc",
						}),
					},
				)

				if (!listResponse.ok) {
					// Return error without profile data - let client preserve existing data
					return Response.json(
						{ error: `API error: ${listResponse.status}` },
						{ status: listResponse.status },
					)
				}

				const listData = await listResponse.json()
				const documents = listData.memories || listData.documents || []

				// Collect all memories from documents
				const staticMemories: string[] = []
				const dynamicMemories: string[] = []
				const seenMemories = new Set<string>()

				// Fetch memories from each document
				for (const doc of documents.slice(0, 10)) {
					try {
						const docResponse = await fetch(
							`${SUPERMEMORY_BASE_URL}/v3/documents/${doc.id}`,
							{
								headers: {
									Authorization: `Bearer ${apiKey}`,
									"Content-Type": "application/json",
								},
							},
						)

						if (docResponse.ok) {
							const docData = await docResponse.json()
							const memories = docData.memories || []

							for (const mem of memories) {
								if (
									mem.memory &&
									!mem.isForgotten &&
									!seenMemories.has(mem.memory)
								) {
									seenMemories.add(mem.memory)
									if (mem.isStatic) {
										staticMemories.push(mem.memory)
									} else {
										dynamicMemories.push(mem.memory)
									}
								}
							}
						}
					} catch (_e) {
						// Skip failed document fetches
					}
				}

				return Response.json({
					profile: {
						static: staticMemories,
						dynamic: dynamicMemories.slice(0, 10), // Limit session to recent 10
					},
				})
			} catch (error: any) {
				console.error("Profile fetch error:", error)
				// Return error without profile data - let client preserve existing data
				return Response.json(
					{ error: error.message || "Profile fetch error" },
					{ status: 500 },
				)
			}
		}

		// Documents API for memory graph
		if (url.pathname === "/api/documents" && request.method === "GET") {
			const userId = url.searchParams.get("userId")
			if (!userId) {
				return Response.json(
					{ error: "userId query parameter is required" },
					{ status: 400 },
				)
			}

			if (!apiKey) {
				return Response.json(
					{ error: "SUPERMEMORY_API_KEY not configured" },
					{ status: 500 },
				)
			}

			try {
				const page = Number.parseInt(url.searchParams.get("page") || "1")
				const limit = Number.parseInt(url.searchParams.get("limit") || "100")

				const response = await fetch(
					`${SUPERMEMORY_BASE_URL}/v3/documents/documents`,
					{
						method: "POST",
						headers: {
							"Content-Type": "application/json",
							Authorization: `Bearer ${apiKey}`,
						},
						body: JSON.stringify({
							page,
							limit,
							sort: "createdAt",
							order: "desc",
							containerTags: [userId],
						}),
					},
				)

				if (!response.ok) {
					const errorText = await response.text()
					console.error(
						"Supermemory documents API error:",
						response.status,
						errorText,
					)
					return Response.json(
						{ error: `API error: ${response.status}` },
						{ status: response.status },
					)
				}

				const data = await response.json()
				return Response.json(data)
			} catch (error: any) {
				return handleApiError(error, "Documents fetch")
			}
		}

		// Health check
		if (url.pathname === "/health") {
			return Response.json({
				status: "ok",
				service: "pipecat-supermemory-demo",
			})
		}

		// For all other routes, return 404 (static assets are served by Cloudflare)
		return new Response("Not found", { status: 404 })
	},
} satisfies ExportedHandler<Env>
