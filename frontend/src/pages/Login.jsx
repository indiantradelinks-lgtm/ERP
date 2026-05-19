import { useState, useEffect } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Eye, EyeOff, ShieldCheck, Lock, Mail, Phone, ArrowRight } from "lucide-react";
import Brand from "@/components/Brand";
import { toast } from "sonner";

export default function Login() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("admin@erp.com");
  const [password, setPassword] = useState("Admin@123");
  const [showPwd, setShowPwd] = useState(false);
  const [loading, setLoading] = useState(false);
  const [phone, setPhone] = useState("");
  const [otp, setOtp] = useState("");
  const [otpSent, setOtpSent] = useState(false);
  const [mockOtp, setMockOtp] = useState("");

  useEffect(() => {
    if (user) navigate("/app", { replace: true });
  }, [user, navigate]);

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    const res = await login(email, password);
    setLoading(false);
    if (res.ok) {
      toast.success(`Welcome, ${res.user.name}`);
      navigate("/app");
    } else {
      toast.error(res.error);
    }
  };

  const sendOtp = () => {
    if (!phone) return toast.error("Enter phone");
    const code = Math.floor(100000 + Math.random() * 900000).toString();
    setMockOtp(code);
    setOtpSent(true);
    toast.info(`Demo OTP: ${code} (mocked)`);
  };
  const verifyOtp = () => {
    if (otp === mockOtp) {
      toast.success("OTP verified (demo). Use email/password for full access.");
    } else {
      toast.error("Invalid OTP");
    }
  };

  return (
    <div className="min-h-screen flex bg-background">
      {/* Left visual */}
      <div className="hidden lg:flex lg:w-1/2 relative overflow-hidden bg-primary text-primary-foreground">
        <img
          src="https://static.prod-images.emergentagent.com/jobs/9aee82b5-a22f-42f7-9330-c146e7cb4c20/images/73f7497aae98b5900f801d77266560bbb884361a717ac9f4a96269908efb7dbb.png"
          alt="Industrial control room"
          className="absolute inset-0 w-full h-full object-cover opacity-25 mix-blend-overlay"
        />
        <div className="absolute inset-0 bg-gradient-to-br from-primary via-primary/95 to-accent/80" />
        <div className="absolute inset-0 industrial-gridlines opacity-15" />
        <div className="relative z-10 flex flex-col justify-between p-10 w-full">
          <Brand />
          <div>
            <div className="text-[10px] font-bold uppercase tracking-[0.2em] text-white/80 mb-3">// CONTROL ROOM</div>
            <h2 className="font-display font-black text-4xl lg:text-5xl leading-[1.05] tracking-tight max-w-md">
              Sign in to your <span className="text-white drop-shadow">command</span> deck.
            </h2>
            <p className="mt-4 text-sm text-white/85 max-w-md">
              Real-time visibility across every project, permit, payroll cycle and purchase order.
            </p>
            <div className="mt-10 grid grid-cols-2 gap-4 max-w-sm">
              <div className="border-l-2 border-white/60 pl-3">
                <div className="font-display font-black text-2xl tabular">256-bit</div>
                <div className="text-[10px] uppercase tracking-[0.18em] text-white/70">Encrypted Sessions</div>
              </div>
              <div className="border-l-2 border-white/60 pl-3">
                <div className="font-display font-black text-2xl tabular">RBAC</div>
                <div className="text-[10px] uppercase tracking-[0.18em] text-white/70">14 Role Levels</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Right form */}
      <div className="flex-1 flex items-center justify-center p-6">
        <div className="w-full max-w-md">
          <div className="lg:hidden mb-8"><Brand /></div>
          <div className="inline-flex items-center gap-2 px-3 py-1.5 border border-border rounded-sm bg-card text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground mb-6">
            <ShieldCheck className="h-3 w-3 text-success" /> Secure Authentication
          </div>
          <h1 className="font-display font-black text-3xl sm:text-4xl tracking-tight">Sign in.</h1>
          <p className="mt-2 text-sm text-muted-foreground">Access your industrial operations console.</p>

          <Tabs defaultValue="password" className="mt-8">
            <TabsList className="grid grid-cols-2 rounded-sm bg-muted/50 p-1 h-10">
              <TabsTrigger value="password" className="rounded-sm text-xs font-bold uppercase tracking-wider" data-testid="login-tab-password">Password</TabsTrigger>
              <TabsTrigger value="otp" className="rounded-sm text-xs font-bold uppercase tracking-wider" data-testid="login-tab-otp">OTP (demo)</TabsTrigger>
            </TabsList>

            <TabsContent value="password" className="mt-6">
              <form onSubmit={submit} className="space-y-4">
                <div>
                  <Label className="text-xs uppercase tracking-wider">Email</Label>
                  <div className="relative mt-1.5">
                    <Mail className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                    <Input value={email} onChange={(e) => setEmail(e.target.value)} className="pl-9 h-11 rounded-sm" data-testid="login-email" required />
                  </div>
                </div>
                <div>
                  <Label className="text-xs uppercase tracking-wider">Password</Label>
                  <div className="relative mt-1.5">
                    <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                    <Input
                      type={showPwd ? "text" : "password"}
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      className="pl-9 pr-10 h-11 rounded-sm"
                      data-testid="login-password"
                      required
                    />
                    <button type="button" onClick={() => setShowPwd((s) => !s)} className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground" data-testid="login-show-password">
                      {showPwd ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                    </button>
                  </div>
                </div>
                <Button type="submit" className="w-full h-11 rounded-sm text-sm font-bold uppercase tracking-wider" disabled={loading} data-testid="login-submit">
                  {loading ? "Signing in…" : <>Sign in <ArrowRight className="h-4 w-4 ml-2" /></>}
                </Button>
                <div className="rounded-sm border border-dashed border-border bg-muted/30 p-3 text-xs text-muted-foreground" data-testid="demo-creds">
                  <span className="font-semibold text-foreground">Demo:</span> admin@erp.com · Admin@123
                </div>
              </form>
            </TabsContent>

            <TabsContent value="otp" className="mt-6">
              <div className="space-y-4">
                <div>
                  <Label className="text-xs uppercase tracking-wider">Phone</Label>
                  <div className="relative mt-1.5">
                    <Phone className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                    <Input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+91 …" className="pl-9 h-11 rounded-sm" data-testid="login-phone" />
                  </div>
                </div>
                {otpSent && (
                  <div>
                    <Label className="text-xs uppercase tracking-wider">OTP Code</Label>
                    <Input value={otp} onChange={(e) => setOtp(e.target.value)} className="h-11 rounded-sm mt-1.5 tracking-[0.4em] text-center font-mono-data" maxLength={6} data-testid="login-otp" />
                  </div>
                )}
                {!otpSent ? (
                  <Button onClick={sendOtp} className="w-full h-11 rounded-sm" data-testid="login-send-otp">Send OTP</Button>
                ) : (
                  <Button onClick={verifyOtp} className="w-full h-11 rounded-sm" data-testid="login-verify-otp">Verify OTP (demo)</Button>
                )}
                <p className="text-xs text-muted-foreground">OTP is mocked in MVP; full Twilio integration available next iteration.</p>
              </div>
            </TabsContent>
          </Tabs>

          <div className="mt-8 text-xs text-muted-foreground flex items-center justify-between">
            <Link to="/" className="hover-amber" data-testid="login-back-home">← Back to home</Link>
            <span>v1.0 · Industrial Build</span>
          </div>
        </div>
      </div>
    </div>
  );
}
