const Index = () => {
  return (
    <main className="min-h-screen bg-background text-foreground flex items-center justify-center px-6">
      <div className="max-w-2xl text-center space-y-6">
        <div className="inline-block px-3 py-1 text-xs font-semibold tracking-widest uppercase border border-border rounded-full">
          BMW Group · Legal AI
        </div>
        <h1 className="text-4xl md:text-5xl font-bold tracking-tight">
          DPA Auditor
        </h1>
        <p className="text-lg text-muted-foreground">
          Initializing your contract review workspace. Upload the Internal Playbook
          and the German law dataset in chat to begin building the full audit flow.
        </p>
        <div className="text-sm text-muted-foreground pt-4">
          Preview is now live ✓
        </div>
      </div>
    </main>
  );
};

export default Index;
