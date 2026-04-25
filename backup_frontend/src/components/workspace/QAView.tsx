import { useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Send, Loader2, MessagesSquare, Sparkles } from "lucide-react";
import ReactMarkdown from "react-markdown";
import { Button } from "@/components/ui/button";
import { askLegalQuestion, formatLegalAnswer } from "@/api/client";
import { toast } from "sonner";

type Msg = { role: "user" | "assistant"; content: string };

const SUGGESTED = [
  "What are the BMW Four-Eyes signature requirements?",
  "Summarize Art. 28 GDPR for a DPA.",
  "What's the breach notification deadline for BMW vendors?",
  "When does a contract require Board of Management approval?",
];

export const QAView = () => {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [contractType, setContractType] = useState("data_protection");
  const [loading, setLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  const send = async (text: string) => {
    const question = text.trim();
    if (!question || loading) return;

    setMessages((current) => [...current, { role: "user", content: question }, { role: "assistant", content: "" }]);
    setInput("");
    setLoading(true);

    try {
      const response = await askLegalQuestion(question, "legal_qa", contractType);
      const content = formatLegalAnswer(response);
      setMessages((current) => {
        const copy = [...current];
        copy[copy.length - 1] = { role: "assistant", content };
        return copy;
      });
      requestAnimationFrame(() => scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" }));
    } catch {
      toast.error("Could not reach the assistant.");
      setMessages((current) => current.slice(0, -1));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-full">
      <div ref={scrollRef} className="flex-1 overflow-y-auto">
        <div className="max-w-3xl mx-auto px-6 py-8">
          {messages.length === 0 ? (
            <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} className="text-center pt-12">
              <div className="h-14 w-14 mx-auto rounded-2xl bg-primary/10 border border-primary/20 grid place-items-center mb-6">
                <MessagesSquare className="h-6 w-6 text-primary" />
              </div>
              <h1 className="text-4xl md:text-5xl font-bold tracking-tight mb-4">Legal Q&amp;A</h1>
              <p className="text-muted-foreground max-w-xl mx-auto mb-10">
                Ask about BMW's contracting playbook, GDPR, German legal evidence, or a legal escalation trigger.
              </p>
              <div className="grid sm:grid-cols-2 gap-3 max-w-2xl mx-auto">
                {SUGGESTED.map((s) => (
                  <button
                    key={s}
                    onClick={() => send(s)}
                    className="rounded-2xl border border-border/60 gradient-card p-4 text-left text-sm hover:border-primary/60 transition-colors"
                  >
                    <Sparkles className="h-4 w-4 text-primary mb-2" />
                    {s}
                  </button>
                ))}
              </div>
            </motion.div>
          ) : (
            <div className="space-y-6">
              <AnimatePresence initial={false}>
                {messages.map((m, i) => (
                  <motion.div
                    key={i}
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    className={m.role === "user" ? "flex justify-end" : "flex gap-3"}
                  >
                    {m.role === "assistant" && (
                      <div className="h-8 w-8 rounded-lg gradient-primary grid place-items-center shrink-0 mt-1">
                        <Sparkles className="h-4 w-4 text-primary-foreground" />
                      </div>
                    )}
                    <div
                      className={
                        m.role === "user"
                          ? "max-w-[80%] rounded-2xl rounded-tr-sm bg-primary text-primary-foreground px-4 py-3 text-sm whitespace-pre-wrap"
                          : "flex-1 min-w-0 rounded-2xl border border-border/60 gradient-card p-4 text-sm"
                      }
                    >
                      {m.role === "assistant" ? (
                        m.content ? (
                          <div className="prose prose-sm prose-invert max-w-none">
                            <ReactMarkdown>{m.content}</ReactMarkdown>
                          </div>
                        ) : (
                          <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                        )
                      ) : (
                        m.content
                      )}
                    </div>
                  </motion.div>
                ))}
              </AnimatePresence>
            </div>
          )}
        </div>
      </div>

      <div className="border-t border-border/60 bg-background/80 backdrop-blur">
        <div className="max-w-3xl mx-auto px-6 py-4">
          <div className="flex items-center justify-between mb-2">
            <div className="text-[10px] uppercase tracking-[0.14em] text-muted-foreground font-semibold">
              Contract Context
            </div>
            <select
              value={contractType}
              onChange={(event) => setContractType(event.target.value)}
              className="bg-card/60 border border-border/70 rounded-md px-3 py-1.5 text-xs focus:outline-none focus:border-primary/60"
            >
              <option value="data_protection">Data protection</option>
              <option value="litigation">Litigation</option>
              <option value="general">General</option>
            </select>
          </div>
          <div className="rounded-2xl border border-border/80 bg-card/60 shadow-card focus-within:border-primary/60 transition-colors flex items-end">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  send(input);
                }
              }}
              placeholder="Ask about a clause, a rule, or a regulation..."
              rows={1}
              className="flex-1 bg-transparent resize-none px-5 py-4 text-sm placeholder:text-muted-foreground focus:outline-none"
            />
            <Button
              size="sm"
              onClick={() => send(input)}
              disabled={loading || !input.trim()}
              className="m-2 gradient-primary border-0 text-primary-foreground"
            >
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
};
