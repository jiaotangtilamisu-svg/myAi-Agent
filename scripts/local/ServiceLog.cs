using System;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Text.RegularExpressions;

// Foreground supervisor: no detach, auto-restart, job assignment or process termination.
public sealed class IndependentServiceLog : IDisposable {
    private readonly Process process;
    private readonly StreamWriter stdout, stderr;
    private readonly string[] secrets;
    private readonly string exitPath;
    private bool exitWritten;
    private readonly object gate = new object();
    public int Pid { get { return process.Id; } }
    public string StartTicks { get { return process.StartTime.ToUniversalTime().Ticks.ToString(); } }
    public IndependentServiceLog(ProcessStartInfo start, string directory, string[] values) {
        secrets = values ?? new string[0];
        exitPath=Path.Combine(directory,"exit.json");
        Array.Sort(secrets, (a,b) => b.Length.CompareTo(a.Length));
        stdout = new StreamWriter(Path.Combine(directory,"stdout.log"),true,new UTF8Encoding(false));
        stderr = new StreamWriter(Path.Combine(directory,"stderr.log"),true,new UTF8Encoding(false));
        stdout.AutoFlush=true; stderr.AutoFlush=true;
        process=new Process(); process.StartInfo=start;
        process.EnableRaisingEvents=true;
        process.Exited += (s,e) => RecordExit();
        process.OutputDataReceived += (s,e) => { if(e.Data!=null) Write(stdout,e.Data); };
        process.ErrorDataReceived += (s,e) => { if(e.Data!=null) Write(stderr,e.Data); };
    }
    private void Write(StreamWriter stream,string line) {
        foreach(string value in secrets) if(!String.IsNullOrEmpty(value)) line=line.Replace(value,"[REDACTED]");
        line=Regex.Replace(line,@"(?i)((?:password|passwd|secret|token|api[_-]?key)\s*[""':=]+\s*)[^\s,;""'}]+","$1[REDACTED]");
        line=Regex.Replace(line,@"(?i)(Bearer\s+)\S+","$1[REDACTED]");
        lock(gate) stream.WriteLine(DateTimeOffset.Now.ToString("o")+" "+line);
    }
    public void Start() { process.Start(); process.BeginOutputReadLine(); process.BeginErrorReadLine(); }
    private void RecordExit() {
        lock(gate) {
            if(exitWritten) return;
            File.WriteAllText(exitPath,"{\"PID\":"+process.Id+",\"ExitCode\":"+process.ExitCode+",\"ExitedAt\":\""+DateTimeOffset.Now.ToString("o")+"\"}",new UTF8Encoding(false));
            exitWritten=true;
        }
    }
    public int WaitForExit() { process.WaitForExit(); RecordExit(); return process.ExitCode; }
    public void Dispose() {
        // If the supervising shell is interrupted, never kill its child here.
        // Keep streams alive while a child is still running; its lifetime is externally observable.
        try { if(!process.HasExited) return; RecordExit(); } catch(InvalidOperationException) {}
        lock(gate) { stdout.Dispose(); stderr.Dispose(); }
        process.Dispose();
    }
}
