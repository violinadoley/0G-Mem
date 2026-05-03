"use client";

import { useState } from "react";
import { useAccount } from "wagmi";
import { useConnect } from "wagmi";
import { injected } from "wagmi/connectors";
import {
  Wallet,
  Bot,
  Cpu,
  Rocket,
  Check,
  Copy,
  ExternalLink,
  ChevronRight,
  AlertCircle,
} from "lucide-react";
import { cn } from "@/lib/utils";

const STEPS = [
  { id: 1, icon: Wallet, title: "Connect Wallet", desc: "Your wallet is your agent identity" },
  { id: 2, icon: Bot, title: "Create Telegram Bot", desc: "Get a bot token from @BotFather" },
  { id: 3, icon: Cpu, title: "0G Compute API Key", desc: "For LLM inference on 0G Labs" },
  { id: 4, icon: Rocket, title: "Deploy", desc: "One-click deploy your own instance" },
];

function CopyBox({ label, value }: { label: string; value: string }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard.writeText(value);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  return (
    <div className="space-y-1.5">
      <p className="text-xs text-muted font-medium">{label}</p>
      <div className="flex items-center gap-2 bg-surface border border-border rounded-lg px-3 py-2">
        <code className="text-xs text-white font-mono flex-1 truncate">{value}</code>
        <button onClick={copy} className="text-muted hover:text-white transition-colors shrink-0">
          {copied ? <Check className="w-3.5 h-3.5 text-green-400" /> : <Copy className="w-3.5 h-3.5" />}
        </button>
      </div>
    </div>
  );
}

function StepCard({
  step,
  active,
  done,
  children,
}: {
  step: (typeof STEPS)[number];
  active: boolean;
  done: boolean;
  children: React.ReactNode;
}) {
  const Icon = step.icon;
  return (
    <div
      className={cn(
        "border rounded-xl p-6 space-y-4 transition-all",
        active ? "border-accent/40 bg-accent/5" : "border-border bg-surface",
        done && "border-green-500/30 bg-green-500/5"
      )}
    >
      <div className="flex items-center gap-3">
        <div
          className={cn(
            "w-9 h-9 rounded-xl flex items-center justify-center border",
            done
              ? "bg-green-500/20 border-green-500/30 text-green-400"
              : active
              ? "bg-accent/20 border-accent/30 text-accent"
              : "bg-surface-raised border-border text-muted"
          )}
        >
          {done ? <Check className="w-4 h-4" /> : <Icon className="w-4 h-4" />}
        </div>
        <div>
          <p className="text-sm font-semibold text-white">{step.title}</p>
          <p className="text-xs text-muted">{step.desc}</p>
        </div>
        <span
          className={cn(
            "ml-auto text-xs font-mono px-2 py-0.5 rounded-full border",
            done
              ? "text-green-400 border-green-500/30 bg-green-500/10"
              : active
              ? "text-accent border-accent/30 bg-accent/10"
              : "text-muted border-border"
          )}
        >
          {done ? "done" : active ? "now" : `0${step.id}`}
        </span>
      </div>
      {active && <div className="space-y-4">{children}</div>}
    </div>
  );
}

async function railwayGql(
  token: string,
  query: string,
  variables?: object
): Promise<Record<string, unknown>> {
  const res = await fetch("/api/railway", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token, query, variables }),
  });
  const json = await res.json();
  if (json.errors) throw new Error(json.errors[0].message);
  return json.data as Record<string, unknown>;
}

export default function DeployPage() {
  const { isConnected, address } = useAccount();
  const { connect, isPending } = useConnect();

  const [botToken, setBotToken] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [serviceUrl, setServiceUrl] = useState("");
  const [agentKey, setAgentKey] = useState("");
  const [railwayToken, setRailwayToken] = useState("");
  const [currentStep, setCurrentStep] = useState(isConnected ? 2 : 1);
  const [deploying, setDeploying] = useState(false);
  const [deployedUrl, setDeployedUrl] = useState("");
  const [deployError, setDeployError] = useState("");

  const step1Done = isConnected;
  const step2Done = botToken.length > 10;
  const step3Done = apiKey.length > 10 && serviceUrl.length > 5;
  const allDone = step1Done && step2Done && step3Done;
  const step4Ready = allDone && agentKey.length > 10 && railwayToken.length > 10;

  async function handleDeploy() {
    setDeploying(true);
    setDeployError("");
    try {
      // 1. Create project
      const { projectCreate } = await railwayGql(
        railwayToken,
        `mutation {
          projectCreate(input: { name: "0g-mem-bot" }) {
            id
            environments { edges { node { id } } }
          }
        }`
      ) as { projectCreate: { id: string; environments: { edges: { node: { id: string } }[] } } };

      const projectId = projectCreate.id;
      const environmentId = projectCreate.environments.edges[0].node.id;

      // 2. Create service linked to GitHub repo
      const { serviceCreate } = await railwayGql(
        railwayToken,
        `mutation serviceCreate($input: ServiceCreateInput!) {
          serviceCreate(input: $input) { id }
        }`,
        { input: { projectId, name: "0g-mem-bot", source: { repo: "Loops-House/0g-Mem" }, branch: "vio" } }
      ) as { serviceCreate: { id: string } };

      const serviceId = serviceCreate.id;

      // 3. Set all env vars (including secrets)
      await railwayGql(
        railwayToken,
        `mutation variableCollectionUpsert($input: VariableCollectionUpsertInput!) {
          variableCollectionUpsert(input: $input)
        }`,
        {
          input: {
            projectId,
            serviceId,
            environmentId,
            variables: {
              AGENT_KEY: agentKey,
              TELEGRAM_BOT_TOKEN: botToken,
              ZEROG_SERVICE_URL: serviceUrl,
              ZEROG_API_KEY: apiKey,
              ZEROG_MODEL: "qwen/qwen-2.5-7b-instruct",
              MEMORY_REGISTRY_ADDRESS: "0xEDF95D9CFb157F5F38C1125B7DFB3968E05d2c4b",
              MEMORY_NFT_ADDRESS: "0x70ad85300f522A41689954a4153744BF6E57E488",
              TOKENIZERS_PARALLELISM: "false",
            },
          },
        }
      );

      setDeployedUrl(`https://railway.app/project/${projectId}`);
    } catch (err) {
      setDeployError(err instanceof Error ? err.message : String(err));
    } finally {
      setDeploying(false);
    }
  }

  return (
    <div className="max-w-2xl mx-auto px-4 sm:px-6 py-12 space-y-8">
      {/* Header */}
      <div className="space-y-2">
        <h1 className="text-3xl font-bold text-white">Deploy Your Agent</h1>
        <p className="text-muted text-sm leading-relaxed">
          Set up your own 0G Mem instance in 4 steps. You own everything — your key, your memory,
          your bot.
        </p>
      </div>

      {/* Progress */}
      <div className="flex items-center gap-2">
        {STEPS.map((s, i) => (
          <div key={s.id} className="flex items-center gap-2 flex-1">
            <div
              className={cn(
                "w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold border",
                (s.id === 1 ? step1Done : s.id === 2 ? step2Done : s.id === 3 ? step3Done : allDone)
                  ? "bg-green-500 border-green-500 text-white"
                  : s.id === currentStep
                  ? "bg-accent border-accent text-white"
                  : "bg-surface border-border text-muted"
              )}
            >
              {(s.id === 1 ? step1Done : s.id === 2 ? step2Done : s.id === 3 ? step3Done : allDone) ? (
                <Check className="w-3 h-3" />
              ) : (
                s.id
              )}
            </div>
            {i < STEPS.length - 1 && (
              <div
                className={cn(
                  "flex-1 h-px",
                  (s.id === 1 ? step1Done : s.id === 2 ? step2Done : s.id === 3 ? step3Done : false)
                    ? "bg-green-500/40"
                    : "bg-border"
                )}
              />
            )}
          </div>
        ))}
      </div>

      {/* Step 1 — Connect Wallet */}
      <StepCard step={STEPS[0]} active={currentStep === 1} done={step1Done}>
        <p className="text-sm text-muted leading-relaxed">
          Your wallet address becomes your <strong className="text-white">Agent ID</strong> — the
          unique identifier for your memory on 0G Chain. No username, no password.
        </p>
        {!isConnected ? (
          <button
            onClick={() => {
              connect({ connector: injected() });
            }}
            disabled={isPending}
            className="flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-semibold bg-accent hover:bg-accent-hover text-white transition-all disabled:opacity-50"
          >
            {isPending ? "Connecting…" : "Connect MetaMask"}
            <ChevronRight className="w-4 h-4" />
          </button>
        ) : (
          <div className="space-y-3">
            <CopyBox label="Your Agent ID (wallet address)" value={address ?? ""} />
            <div className="flex items-start gap-2 text-xs text-yellow-400/80 bg-yellow-500/10 border border-yellow-500/20 rounded-lg px-3 py-2.5">
              <AlertCircle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
              <span>
                You&apos;ll need to export your private key from MetaMask to use as{" "}
                <code className="font-mono">AGENT_KEY</code> in the next step. Settings → Account
                Details → Export Private Key.
              </span>
            </div>
            <button
              onClick={() => setCurrentStep(2)}
              className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-surface-raised hover:bg-surface border border-border text-white transition-all"
            >
              Continue <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        )}
      </StepCard>

      {/* Step 2 — Telegram Bot */}
      <StepCard step={STEPS[1]} active={currentStep === 2} done={step2Done}>
        <ol className="text-sm text-muted space-y-2 list-decimal list-inside leading-relaxed">
          <li>
            Open Telegram and message{" "}
            <a
              href="https://t.me/BotFather"
              target="_blank"
              rel="noopener noreferrer"
              className="text-accent hover:underline inline-flex items-center gap-1"
            >
              @BotFather <ExternalLink className="w-3 h-3" />
            </a>
          </li>
          <li>
            Send <code className="font-mono text-white">/newbot</code>
          </li>
          <li>Choose a name and username for your bot</li>
          <li>Copy the token BotFather gives you</li>
        </ol>
        <div className="space-y-2">
          <label className="text-xs text-muted font-medium">Paste your bot token</label>
          <input
            type="text"
            value={botToken}
            onChange={(e) => setBotToken(e.target.value)}
            placeholder="1234567890:AAF..."
            className="w-full bg-surface border border-border rounded-lg px-3 py-2 text-sm text-white font-mono placeholder:text-muted/50 focus:outline-none focus:border-accent/50 transition-colors"
          />
        </div>
        {step2Done && (
          <button
            onClick={() => setCurrentStep(3)}
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-surface-raised hover:bg-surface border border-border text-white transition-all"
          >
            Continue <ChevronRight className="w-4 h-4" />
          </button>
        )}
      </StepCard>

      {/* Step 3 — 0G Compute */}
      <StepCard step={STEPS[2]} active={currentStep === 3} done={step3Done}>
        <p className="text-sm text-muted leading-relaxed">
          0G Compute provides LLM inference running on 0G Labs decentralized infrastructure. Your
          agent uses this for all AI responses.
        </p>
        <ol className="text-sm text-muted space-y-2 list-decimal list-inside leading-relaxed">
          <li>
            Install the CLI:{" "}
            <code className="font-mono text-white text-xs">npm install -g 0g-compute-cli</code>
          </li>
          <li>
            Run: <code className="font-mono text-white text-xs">0g-compute-cli login</code>
          </li>
          <li>
            Create account:{" "}
            <code className="font-mono text-white text-xs">
              0g-compute-cli inf add-account --amount 3
            </code>
          </li>
          <li>
            Get your Service URL + API key:{" "}
            <code className="font-mono text-white text-xs">
              0g-compute-cli inf get-secret
            </code>
            {" "}— prints both values, paste them below
          </li>
        </ol>
        <div className="space-y-3">
          <div className="space-y-2">
            <label className="text-xs text-muted font-medium">Service URL</label>
            <input
              type="text"
              value={serviceUrl}
              onChange={(e) => setServiceUrl(e.target.value)}
              placeholder="https://compute-network-X.integratenetwork.work"
              className="w-full bg-surface border border-border rounded-lg px-3 py-2 text-sm text-white font-mono placeholder:text-muted/50 focus:outline-none focus:border-accent/50 transition-colors"
            />
          </div>
          <div className="space-y-2">
            <label className="text-xs text-muted font-medium">API Key</label>
            <input
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="app-sk-..."
              className="w-full bg-surface border border-border rounded-lg px-3 py-2 text-sm text-white font-mono placeholder:text-muted/50 focus:outline-none focus:border-accent/50 transition-colors"
            />
          </div>
        </div>
        {step3Done && (
          <button
            onClick={() => setCurrentStep(4)}
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-surface-raised hover:bg-surface border border-border text-white transition-all"
          >
            Continue <ChevronRight className="w-4 h-4" />
          </button>
        )}
      </StepCard>

      {/* Step 4 — Deploy */}
      <StepCard step={STEPS[3]} active={currentStep === 4} done={!!deployedUrl}>
        {allDone ? (
          <div className="space-y-4">
            {deployedUrl ? (
              <div className="space-y-3">
                <div className="flex items-start gap-2 text-xs text-green-400/80 bg-green-500/10 border border-green-500/20 rounded-lg px-3 py-2.5">
                  <Check className="w-3.5 h-3.5 mt-0.5 shrink-0" />
                  <span>Bot deployed! Railway is building your image now (~3 min).</span>
                </div>
                <a
                  href={deployedUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-semibold bg-accent hover:bg-accent-hover text-white transition-all w-fit"
                >
                  Open Railway Project <ExternalLink className="w-3.5 h-3.5" />
                </a>
              </div>
            ) : (
              <>
                <p className="text-sm text-muted leading-relaxed">
                  Enter your private key and a Railway API token — we&apos;ll create the project,
                  link the repo, and set all env vars automatically.
                </p>

                <div className="space-y-3">
                  <div className="space-y-2">
                    <label className="text-xs text-muted font-medium">
                      Agent Key (MetaMask private key)
                    </label>
                    <input
                      type="password"
                      value={agentKey}
                      onChange={(e) => setAgentKey(e.target.value)}
                      placeholder="0x..."
                      className="w-full bg-surface border border-border rounded-lg px-3 py-2 text-sm text-white font-mono placeholder:text-muted/50 focus:outline-none focus:border-accent/50 transition-colors"
                    />
                    <p className="text-xs text-muted">
                      MetaMask → Settings → Account Details → Export Private Key
                    </p>
                  </div>

                  <div className="space-y-2">
                    <label className="text-xs text-muted font-medium">Railway API Token</label>
                    <input
                      type="password"
                      value={railwayToken}
                      onChange={(e) => setRailwayToken(e.target.value)}
                      placeholder="railway_token_..."
                      className="w-full bg-surface border border-border rounded-lg px-3 py-2 text-sm text-white font-mono placeholder:text-muted/50 focus:outline-none focus:border-accent/50 transition-colors"
                    />
                    <p className="text-xs text-muted">
                      Get one at{" "}
                      <a
                        href="https://railway.app/account/tokens"
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-accent hover:underline"
                      >
                        railway.app/account/tokens
                      </a>{" "}
                      — takes 10 seconds
                    </p>
                  </div>
                </div>

                {deployError && (
                  <div className="flex items-start gap-2 text-xs text-red-400/80 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2.5">
                    <AlertCircle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
                    <span>{deployError}</span>
                  </div>
                )}

                <div className="flex items-start gap-2 text-xs text-yellow-400/80 bg-yellow-500/10 border border-yellow-500/20 rounded-lg px-3 py-2.5">
                  <AlertCircle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
                  <span>
                    Your private key and API keys are sent directly to Railway&apos;s API over
                    HTTPS. They are never stored on our servers.
                  </span>
                </div>

                <div className="flex flex-col sm:flex-row gap-3">
                  <button
                    onClick={handleDeploy}
                    disabled={!step4Ready || deploying}
                    className="flex items-center gap-2 px-5 py-3 rounded-xl text-sm font-semibold bg-accent hover:bg-accent-hover text-white transition-all disabled:opacity-40"
                  >
                    <Rocket className="w-4 h-4" />
                    {deploying ? "Deploying…" : "Deploy My Bot"}
                  </button>
                  <a
                    href="https://railway.com/deploy/8vaCZl"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center justify-center gap-2 px-5 py-3 rounded-xl text-sm font-medium border border-border hover:border-accent text-muted hover:text-white transition-all"
                  >
                    Deploy manually <ExternalLink className="w-3.5 h-3.5" />
                  </a>
                </div>
              </>
            )}
          </div>
        ) : (
          <p className="text-sm text-muted">Complete the steps above to unlock deployment.</p>
        )}
      </StepCard>
    </div>
  );
}
