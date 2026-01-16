import { defineConfig } from "drizzle-kit"

export default defineConfig({
	dialect: "sqlite",
	schema: "./auth-schema.ts",
	out: "./drizzle",
	driver: "d1-http",
	dbCredentials: {
		accountId: "47c2b4d598af9d423c06fc9f936226d5",
		databaseId: "58c07e1b-a638-492b-8006-ea05dc64220b",
		token: process.env.CLOUDFLARE_D1_TOKEN || "",
	},
})
