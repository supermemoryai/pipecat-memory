/* eslint-disable */
// Pipecat + Supermemory Voice Demo environment types
declare namespace Cloudflare {
	interface GlobalProps {
		mainModule: typeof import("./src/server")
	}
	interface Env {
		SUPERMEMORY_API_KEY?: string
	}
}
interface Env extends Cloudflare.Env {}
type StringifyValues<EnvType extends Record<string, unknown>> = {
	[Binding in keyof EnvType]: EnvType[Binding] extends string
		? EnvType[Binding]
		: string
}
declare namespace NodeJS {
	interface ProcessEnv
		extends StringifyValues<Pick<Cloudflare.Env, "SUPERMEMORY_API_KEY">> {}
}
