package com.maxhub.gps;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.media.AudioAttributes;
import android.media.AudioManager;
import android.media.MediaPlayer;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import android.speech.RecognizerIntent;
import android.speech.tts.TextToSpeech;
import android.speech.tts.Voice;
import android.speech.tts.UtteranceProgressListener;
import android.text.InputType;
import android.util.AtomicFile;
import android.view.Gravity;
import android.view.View;
import android.view.WindowInsets;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import org.json.JSONArray;
import org.json.JSONObject;

public final class MainActivity extends Activity {
    static final int BG=0xff0d1722, PANEL=0xff1b2c3d, LINE=0xff31485d, INK=0xfff3f8fc,
        MUTED=0xffb0c0d0, MINT=0xff75f0de, DARK=0xff0e2932;
    static final Locale PT=new Locale("pt","BR");
    static final int SPEECH=51;
    final Handler ui=new Handler(Looper.getMainLooper());
    final ExecutorService network=Executors.newSingleThreadExecutor();
    final ExecutorService routing=Executors.newSingleThreadExecutor();
    final ExecutorService commands=Executors.newSingleThreadExecutor();
    final ExecutorService voiceNetwork=Executors.newSingleThreadExecutor();
    final ExecutorService mapNetwork=Executors.newSingleThreadExecutor();
    final Set<String> announced=new HashSet<>();
    final ArrayList<Integer> stops=new ArrayList<>();
    SharedPreferences settings;
    volatile HubConnection hub;
    TextToSpeech tts;
    MediaPlayer audio;
    File audioClip;
    String speakingPhrase="";
    int voiceSequence;
    boolean speakingTest, voiceBusy, installingVoice;
    TextView voiceStatus;
    String voiceMessage="";
    boolean speechReady, visible, polling, demo, choosing, planning;
    int tab, pollCount, routeGeneration, waypointMode;
    long demoStart, lastSpeedWarning, nextMapTry;
    boolean mapDownloading;
    String mapStatus="", cachedMapId="";
    boolean speeding, realTime, freightRoute;
    String lastFreight="";
    TextView fuelGauge;
    float speechRate=1, speechPitch=1;
    String voice="", voiceOutput="off", scope="default", mapId="", alertScope="";
    int alertRevision=-1;
    JSONObject truck;
    JSONArray alerts=new JSONArray();
    RoadMap map, savedMap;
    RoadMap.Route route;
    MapView mapView;
    FrameLayout body;
    LinearLayout footer, mediaResults;
    TextView connection, maneuver, maneuverDetail, mapCaption, speed, limit, tripBar, hazard,
        tripDetails, mediaStatus;
    Button[] tabs;
    AtomicFile cache;
    final Runnable tick=this::tick;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        settings=getPreferences(MODE_PRIVATE);
        hub=HubConnection.parse(settings.getString("hub",""));
        if(hub!=null)hub=new HubConnection(hub.origin.getHost(),hub.origin.getPort(),hub.token,settings.getString("hub_name",hub.name));
        voiceOutput=settings.getString("voice_output","off");
        voice=settings.getString("voice_name","");
        speechRate=settings.getFloat("voice_rate",1);
        speechPitch=settings.getFloat("voice_pitch",1);
        cache=new AtomicFile(new File(getFilesDir(),"active-map.json"));
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        setVolumeControlStream(AudioManager.STREAM_MUSIC);
        getWindow().setStatusBarColor(BG);getWindow().setNavigationBarColor(BG);
        build();
        initializeSpeech();
        network.execute(() -> {
            try {
                byte[] bytes=cache.readFully();
                RoadMap candidate=decodeMap(bytes);
                String id=hash(bytes);
                ui.post(() -> {
                    savedMap=candidate;
                    cachedMapId=id;
                });
            } catch(Exception ignored) {}
        });
        if(!openPairLink(getIntent()) && hub==null)ui.postDelayed(this::discover,450);
    }

    @Override protected void onResume() {
        super.onResume();
        visible=true;
        if(installingVoice){installingVoice=false;initializeSpeech();}
        ui.removeCallbacks(tick);
        ui.post(tick);
    }

    @Override protected void onPause() {
        visible=false;
        ui.removeCallbacks(tick);
        super.onPause();
    }

    @Override protected void onDestroy() {
        ui.removeCallbacksAndMessages(null);
        network.shutdownNow();routing.shutdownNow();commands.shutdownNow();voiceNetwork.shutdownNow();mapNetwork.shutdownNow();
        if(tts!=null) {tts.stop();tts.shutdown();}
        releaseAudio();
        super.onDestroy();
    }

    int dp(float v) { return Math.round(v*getResources().getDisplayMetrics().density); }
    LinearLayout stack(boolean vertical) {
        LinearLayout box=new LinearLayout(this);
        box.setOrientation(vertical?LinearLayout.VERTICAL:LinearLayout.HORIZONTAL);
        return box;
    }
    GradientDrawable surface(int color,int stroke,int radius) {
        GradientDrawable shape=new GradientDrawable();
        shape.setColor(color);
        shape.setCornerRadius(dp(radius));
        if(stroke!=0) shape.setStroke(dp(1),stroke);
        return shape;
    }
    TextView text(String value,int size,int color,boolean bold) {
        TextView label=new TextView(this);
        label.setText(value);label.setTextSize(size);label.setTextColor(color);
        if(bold) label.setTypeface(Typeface.create("sans-serif-medium",Typeface.NORMAL));
        return label;
    }
    Button button(String caption,Runnable touch) {
        Button button=new Button(this);
        button.setText(caption);button.setAllCaps(false);button.setTextSize(13);
        button.setTextColor(INK);button.setMinHeight(dp(42));button.setMinimumHeight(dp(42));
        button.setPadding(dp(10),dp(4),dp(10),dp(4));
        button.setBackground(surface(PANEL,LINE,12));
        button.setOnClickListener(view -> touch.run());
        return button;
    }
    void inset(LinearLayout layout, int size) { layout.setPadding(dp(size),dp(size),dp(size),dp(size)); }
    void vertical(LinearLayout layout,View child,int top) {
        LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(-1,-2);
        p.topMargin=dp(top);layout.addView(child,p);
    }
    void item(LinearLayout row,View child,int space) {
        LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(0,-2,1);
        p.rightMargin=dp(space);row.addView(child,p);
    }
    LinearLayout section(FrameLayout parent) {
        ScrollView scroll=new ScrollView(this);scroll.setFillViewport(true);
        parent.addView(scroll,new FrameLayout.LayoutParams(-1,-1));
        LinearLayout column=stack(true);inset(column,16);
        scroll.addView(column,new ScrollView.LayoutParams(-1,-2));return column;
    }

    void build() {
        LinearLayout base=stack(true);base.setBackgroundColor(BG);
        if(Build.VERSION.SDK_INT>=30) base.setOnApplyWindowInsetsListener((v,insets) -> {
            android.graphics.Insets areas=insets.getInsets(WindowInsets.Type.systemBars()|WindowInsets.Type.displayCutout());
            v.setPadding(areas.left,areas.top,areas.right,areas.bottom);return WindowInsets.CONSUMED;
        });
        LinearLayout header=stack(false);header.setGravity(Gravity.CENTER_VERTICAL);header.setPadding(dp(16),dp(8),dp(12),dp(8));
        LinearLayout wordmark=stack(true);
        wordmark.addView(text("Max GPS",23,INK,true));
        connection=text("Procurar o Max Hub",12,MUTED,false);
        wordmark.addView(connection);
        header.addView(wordmark,new LinearLayout.LayoutParams(0,-2,1));
        header.addView(button("Conectar",this::discover));
        base.addView(header);
        body=new FrameLayout(this);
        base.addView(body,new LinearLayout.LayoutParams(-1,0,1));
        footer=stack(false);footer.setPadding(dp(10),dp(7),dp(10),dp(7));
        String[] names={"Mapa","Viagem","Multimídia","Ajustes"};
        tabs=new Button[names.length];
        for(int i=0;i<names.length;i++) {
            int index=i;tabs[i]=button(names[i],()->select(index));item(footer,tabs[i],i==names.length-1?0:5);
        }
        base.addView(footer);setContentView(base);select(0);
    }

    void select(int index) {
        tab=index;
        for(int i=0;i<tabs.length;i++) {
            tabs[i].setBackground(surface(i==index?MINT:PANEL,i==index?0:LINE,12));
            tabs[i].setTextColor(i==index?DARK:INK);
        }
        body.removeAllViews();voiceStatus=null;
        mapView=null;tripDetails=null;mediaResults=null;
        if(index==0) buildMap();
        else if(index==1) {
            LinearLayout list=section(body);
            vertical(list,text("Computador de bordo",25,INK,true),0);
            tripDetails=text("",17,INK,false);tripDetails.setLineSpacing(dp(8),1);
            insetCard(tripDetails);vertical(list,tripDetails,12);
            vertical(list,button("Marcar alerta na posição atual",this::markAlert),10);
            vertical(list,button("Minhas marcações",this::manageAlerts),8);
        } else if(index==2) buildMedia();
        else buildSettings();
        display();
    }

    void insetCard(TextView label) {
        label.setPadding(dp(14),dp(12),dp(14),dp(12));
        label.setBackground(surface(PANEL,LINE,14));
    }
    void place(FrameLayout canvas, View view,int gravity,int left,int top,int right,int bottom,int width) {
        FrameLayout.LayoutParams p=new FrameLayout.LayoutParams(width,-2,gravity);
        p.setMargins(dp(left),dp(top),dp(right),dp(bottom));
        canvas.addView(view,p);
    }
    void buildMap() {
        FrameLayout canvas=new FrameLayout(this);
        body.addView(canvas,new FrameLayout.LayoutParams(-1,-1));
        mapView=new MapView(this,this::pin);
        canvas.addView(mapView,new FrameLayout.LayoutParams(-1,-1));
        mapView.setMap(map);mapView.route=route;mapView.stops=new ArrayList<>(stops);
        LinearLayout turn=stack(true);inset(turn,12);turn.setBackground(surface(0xf11b2c3d,LINE,15));
        maneuver=text("",22,INK,true);maneuverDetail=text("",12,MUTED,false);
        turn.addView(maneuver);turn.addView(maneuverDetail);
        place(canvas,turn,Gravity.TOP|Gravity.LEFT,11,11,11,0,Math.min(dp(270),getResources().getDisplayMetrics().widthPixels-dp(22)));
        hazard=text("",14,0xffffddae,true);insetCard(hazard);
        hazard.setBackground(surface(0xf14b331f,0xffbf874e,12));
        place(canvas,hazard,Gravity.TOP|Gravity.LEFT,12,91,12,0,-2);
        LinearLayout zoom=stack(true);
        for(String label:new String[]{"+","−","⌖"}) {
            vertical(zoom,button(label,()->{ if(label.equals("⌖"))mapView.center();else mapView.zoom(label.equals("+")?1.4f:1/1.4f); }),4);
        }
        vertical(zoom,button("Vista",()->mapView.tilt()),4);
        place(canvas,zoom,Gravity.BOTTOM|Gravity.RIGHT,0,0,12,162,dp(62));
        LinearLayout gauge=stack(true);inset(gauge,9);gauge.setBackground(surface(0xf01b2c3d,LINE,16));
        speed=text("—",31,INK,true);limit=text("",12,0xffffc3a8,true);
        gauge.addView(speed);gauge.addView(text("km/h",11,MUTED,false));gauge.addView(limit);
        place(canvas,gauge,Gravity.BOTTOM|Gravity.LEFT,12,0,0,101,-2);
        fuelGauge=text("",14,INK,true);insetCard(fuelGauge);
        place(canvas,fuelGauge,Gravity.BOTTOM|Gravity.RIGHT,0,0,12,102,-2);
        LinearLayout bottom=stack(true);inset(bottom,9);bottom.setBackground(surface(0xf61b2c3d,LINE,15));
        tripBar=text("",15,INK,true);mapCaption=text("",11,MUTED,false);
        tripBar.setOnClickListener(v->{realTime=!realTime;display();});
        bottom.addView(tripBar);bottom.addView(mapCaption);
        LinearLayout actions=stack(false);
        item(actions,button("Destino",()->startPin(false)),5);
        item(actions,button("+ Parada",this::chooseStop),5);
        item(actions,button("Limpar",this::clearRoute),0);
        vertical(bottom,actions,5);
        place(canvas,bottom,Gravity.BOTTOM|Gravity.LEFT,10,0,10,8,-1);
    }

    RoadMap decodeMap(byte[] bytes) throws Exception {
        if(bytes.length<2 || bytes.length>HubConnection.MAX_MAP) throw new IllegalArgumentException("Mapa inválido");
        return new RoadMap(new JSONObject(new String(bytes,StandardCharsets.UTF_8)));
    }
    static String hash(byte[] bytes) throws Exception {
        byte[] digest=MessageDigest.getInstance("SHA-256").digest(bytes);
        StringBuilder text=new StringBuilder();
        for(byte b:digest) text.append(String.format(Locale.ROOT,"%02x",b&255));
        return text.toString();
    }

    void setMap(RoadMap graph,String id) {
        lastFreight="";freightRoute=false;map=graph;mapId=id;route=null;routeGeneration++;planning=false;stops.clear();choosing=false;
        if(mapView!=null) {mapView.selecting=false;mapView.setMap(graph);}
    }

    void tick() {
        if(!visible || isDestroyed()) return;
        if(demo) {
            truck=demoTruck((SystemClock.elapsedRealtime()-demoStart)/1000.);
            display();
        } else if(hub!=null && !polling) {
            HubConnection active=hub;
            String priorAlerts=alertScope;
            int priorRevision=alertRevision;
            polling=true;
            network.execute(() -> poll(active,priorAlerts,priorRevision));
        }
        ui.postDelayed(tick,demo?170:470);
    }

    void poll(HubConnection active,String priorAlerts,int priorRevision) {
        try {
            JSONObject state=active.json("/telemetria",null);
            JSONObject features=state.optJSONObject("features");
            boolean gps=features!=null&&features.optBoolean("gps");
            boolean media=features!=null&&features.optBoolean("media");
            String current=state.optString("mapScope", state.optInt("mapRevision")>0?"legacy":"default");
            JSONObject freshAlerts=null;
            if(gps&&(!current.equals(priorAlerts)||state.optInt("alertRevision",-1)!=priorRevision||++pollCount%12==0)) {
                try {freshAlerts=active.json("/alertas",null);} catch(Exception ignored) {}
            }
            JSONObject roadAlerts=freshAlerts;
            ui.post(() -> {
                polling=false;
                if(isDestroyed()||active!=hub||demo) return;
                if(!gps) {
                    scope="";
                    if(map!=null) setMap(null,"");
                    truck=null;
                    alerts=new JSONArray();
                    alertScope="";alertRevision=-1;
                    mapStatus=features==null?"Atualize o Max Hub para usar este APK":
                        "Ative o Max GPS com sua chave no Hub";
                    connection.setText(media?"Max Multimídia conectado":mapStatus);
                    display();
                    return;
                }
                if(!current.equals(scope)) nextMapTry=0;
                scope=current;
                if(current.equals("default")) {
                    if(!current.equals(mapId)) setMap(null,current);
                    mapStatus="Gere o mapa do perfil no Max Hub";
                } else if(!current.equals(mapId)&&current.equals(cachedMapId)&&savedMap!=null) {
                    setMap(savedMap,current);
                    mapStatus="";
                } else if(!current.equals(mapId)) {
                    if(map!=null) setMap(null,"");
                    if(!mapDownloading && SystemClock.elapsedRealtime()>=nextMapTry) downloadMap(active,current);
                }
                if(roadAlerts!=null) {
                    if(!alertScope.equals(roadAlerts.optString("scope"))) announced.clear();
                    alertScope=roadAlerts.optString("scope");
                    alertRevision=roadAlerts.optInt("revision");
                    alerts=roadAlerts.optJSONArray("points");
                    if(alerts==null) alerts=new JSONArray();
                }
                truck=state.optJSONObject("truck");
                connection.setText(truck==null?"Max Hub conectado · aguardando ETS2":"ETS2 ao vivo · "+active.name);
                display();
            });
        } catch(Exception fail) {
            ui.post(() -> {
                polling=false;
                if(isDestroyed()||active!=hub||demo) return;
                truck=null;
                connection.setText("Reconectando ao Max Hub…");
                display();
            });
        }
    }

    void downloadMap(HubConnection active,String expected) {
        mapDownloading=true;
        mapStatus="Baixando o mapa do Max Hub…";
        mapNetwork.execute(() -> {
            RoadMap graph=null;
            String status="";
            try {
                byte[] bytes=active.request("/mapa",null,HubConnection.MAX_MAP);
                if(!expected.equals("legacy") && !hash(bytes).equals(expected))
                    throw new java.io.IOException("o mapa do Hub mudou");
                graph=decodeMap(bytes);
                try {
                    FileOutputStream output=cache.startWrite();
                    try {output.write(bytes);cache.finishWrite(output);}
                    catch(Exception fail){cache.failWrite(output);throw fail;}
                } catch(Exception fail) {
                    status="Mapa disponível nesta sessão · falha ao salvar no celular";
                }
            } catch(Exception fail) {
                status="Falha ao baixar o mapa · "+(fail.getMessage()==null?"tentando novamente":fail.getMessage());
            }
            RoadMap downloaded=graph;
            String result=status;
            ui.post(() -> {
                mapDownloading=false;
                if(isDestroyed()||active!=hub||demo||!scope.equals(expected)) return;
                mapStatus=result;
                if(downloaded!=null) {savedMap=downloaded;cachedMapId=expected;setMap(downloaded,expected);}
                else nextMapTry=SystemClock.elapsedRealtime()+5500;
                display();
            });
        });
    }

    void chooseStop() {
        if(map==null || route==null || truck==null || planning || stops.size()>=9){startPin(true);return;}
        RoadMap selected=map;
        RoadMap.Route current=route;
        int first=current.segment;
        double progress=current.progress;
        routing.execute(()->{
            // Search a corridor ahead instead of suggesting a stop behind the truck.
            java.util.Map<String,RoadMap.Place> choices=new java.util.LinkedHashMap<>();
            for(int i=first;i+1<current.nodes.length && current.cumulative[i]-progress<4000 && choices.size()<3;i++) {
                int a=current.nodes[i],b=current.nodes[i+1];
                double dx=selected.x[b]-selected.x[a], dz=selected.z[b]-selected.z[a];
                double length=selected.distance(a,b);
                if(length==0)continue;
                for(RoadMap.Place place:selected.places){
                    if(place.type.equals("company")||choices.containsKey(place.type))continue;
                    double x=place.x-selected.x[a],z=place.z-selected.z[a];
                    double t=Math.max(0,Math.min(1,(x*dx+z*dz)/(length*length)));
                    double at=current.cumulative[i]+t*length-progress;
                    if(at>=0 && at<=4000 && Math.hypot(x-t*dx,z-t*dz)<=120) choices.put(place.type,place);
                }
            }
            ui.post(()->{
                if(isDestroyed()||selected!=map||current!=route)return;
                ArrayList<RoadMap.Place> places=new ArrayList<>(choices.values());
                String[] options=new String[places.size()+1];options[0]="Escolher no mapa";
                for(int i=0;i<places.size();i++) {
                    String kind=places.get(i).type;
                    options[i]=kind.equals("fuel")?"Posto na rota":kind.equals("rest")?"Descanso na rota":"Oficina na rota";
                }
                new AlertDialog.Builder(this).setTitle("Adicionar parada").setItems(options,(d,i)->{
                    if(current!=route || selected!=map)return;
                    startPin(true);
                    if(i>0 && choosing){RoadMap.Place place=places.get(i-1);pin(place.x,place.z);}
                }).show();
            });
        });
    }

    void startPin(boolean append) {
        if(planning && !freightRoute)return;
        if(map==null || truck==null) {toast("Carregue um mapa e entre na cabine ou use a demonstração.");return;}
        if(append&&stops.isEmpty()) {toast("Escolha o destino primeiro.");return;}
        if(append&&stops.size()>=9) {toast("Limite de oito paradas intermediárias.");return;}
        if (planning && freightRoute) {routeGeneration++;planning=false;}
        freightRoute=false;choosing=true;waypointMode=append?1:0;if(mapView!=null)mapView.selecting=true;display();
    }

    void pin(double x,double z) {
        if(!choosing||map==null||truck==null||planning) return;
        RoadMap selected=map;
        double truckX=truck.optDouble("x"),truckZ=truck.optDouble("z");
        ArrayList<Integer> requested=new ArrayList<>(stops);
        final int generation=++routeGeneration;
        final boolean insert=waypointMode==1;
        planning=true;display();
        routing.execute(() -> {
            int start=selected.nearest(truckX,truckZ,270), destination=selected.nearest(x,z,140);
            if(destination>=0) {
                if(insert) requested.add(requested.size()-1,destination);
                else {requested.clear();requested.add(destination);}
            }
            RoadMap.Route result=start>=0&&destination>=0?selected.plan(start,requested):null;
            ui.post(() -> {
                if(isDestroyed()||selected!=map||generation!=routeGeneration)return;
                planning=false;
                if(result==null) {toast("Nenhuma rota para esse ponto. Toque em outra via.");display();return;}
                stops.clear();stops.addAll(requested);route=result;choosing=false;
                if(mapView!=null) {mapView.selecting=false;mapView.center();}
                display();
            });
        });
    }

    void clearRoute() {
        freightRoute=false;route=null;stops.clear();choosing=false;planning=false;routeGeneration++;
        if(mapView!=null) mapView.selecting=false;
        display();
    }

    String numeric(String key, double scale, String unit) {
        double value=truck==null?-1:truck.optDouble(key,-1);
        return value<0?"—":String.format(PT,"%.0f%s",value*scale,unit);
    }

    String roadWarning() {
        if(truck==null||truck.optBoolean("paused")||truck.optDouble("speed")<1) return "";
        double x=truck.optDouble("x"),z=truck.optDouble("z"),heading=truck.optDouble("heading");
        double fx=-Math.sin(heading*Math.PI*2),fz=-Math.cos(heading*Math.PI*2);
        double range=Math.max(80,Math.min(300,25+truck.optDouble("speed")*8)), closest=range;
        JSONObject selected=null;
        for(int i=0;i<alerts.length();i++) {
            JSONObject point=alerts.optJSONObject(i);
            if(point==null)continue;
            double px=point.optDouble("x")-x,pz=point.optDouble("z")-z,meters=Math.hypot(px,pz);
            if(meters>450)announced.remove(point.optString("id"));
            if(px*fx+pz*fz<=3 || Math.abs(px*fz-pz*fx)>32 || meters>=closest)continue;
            if(point.has("heading")&&Math.cos((point.optDouble("heading")-heading)*Math.PI*2)<.45)continue;
            closest=meters;selected=point;
        }
        if(selected==null)return "";
        String kind=labelAlert(selected.optString("type"));
        if(announced.add(selected.optString("id")))speak(selected.optString("type").equals("radar")?VoiceCue.CAMERA:
                selected.optString("type").equals("bump")?VoiceCue.BUMP:VoiceCue.CHECKPOINT,0,false);
        return kind+" · "+Math.round(closest)+" m";
    }

    void followFreight() {
        if (truck==null || map==null || choosing || (route!=null && !freightRoute)) return;
        String city=truck.optString("cityId"), company=truck.optString("companyId");
        String job=city.isEmpty()||company.isEmpty()?"":city+"/"+company;
        if (job.equals(lastFreight)) return;
        lastFreight=job;
        if (freightRoute) clearRoute();
        if (job.isEmpty() || planning) return;
        RoadMap.Place match=null;
        for (RoadMap.Place place:map.places) {
            if (city.equals(place.city) && company.equals(place.company)) {
                if (match!=null) return; // Multiple depots: let the driver choose.
                match=place;
            }
        }
        if (match==null) return;
        final RoadMap.Place depot=match;
        final RoadMap selected=map;
        final double x=truck.optDouble("x"),z=truck.optDouble("z");
        final int generation=++routeGeneration;
        freightRoute=true;planning=true;
        routing.execute(()->{
            int start=selected.nearest(x,z,270),end=selected.nearest(depot.x,depot.z,140);
            RoadMap.Route planned=start>=0&&end>=0?selected.plan(start,Collections.singletonList(end)):null;
            ui.post(()->{
                if(isDestroyed()||generation!=routeGeneration||map!=selected)return;
                planning=false;route=planned;
                if(planned!=null){stops.clear();stops.add(end);}
                display();
            });
        });
    }

    void display() {
        followFreight();
        String warning=roadWarning();
        String turn=truck==null?"Aguardando o caminhão":"Acompanhando o caminhão";
        String detail=map==null?"Importe um mapa rodoviário pelo Max Hub.":"Toque em Destino para traçar uma rota.";
        if(choosing) {
            turn=planning?"Calculando a rota…":"Toque na via";
            detail=waypointMode==1?"Escolha uma parada intermediária.":"Escolha o ponto de chegada.";
        } else if(route!=null&&truck!=null&&map!=null) {
            if(!route.advance(map,truck.optDouble("x"),truck.optDouble("z"))) {
                turn="Fora da rota";detail="Escolha o destino novamente para recalcular.";
            } else {
                int i=0;
                while(i<route.steps.size()&&route.steps.get(i).at-route.progress<8)i++;
                if(i==route.steps.size()) {
                    turn="Destino alcançado";detail="";
                    if(route.spoken<i&&!truck.optBoolean("paused")) {route.spoken=i;speak(VoiceCue.ARRIVED,0,false);}
                } else {
                    RoadMap.Step step=route.steps.get(i);
                    int meters=(int)(step.at-route.progress);
                    turn=meters+" m   "+step.glyph+"  "+step.text;
                    if(i+1<route.steps.size()) {
                        RoadMap.Step next=route.steps.get(i+1);
                        detail="Depois   "+next.glyph+"   "+Math.round(next.at-step.at)+" m";
                    } else detail="Última manobra";
                    for(int j=route.segment;j+1<route.nodes.length && route.cumulative[j]-route.progress<160;j++) {
                        String hint=map.lanes.get(RoadMap.edgeKey(route.nodes[j],route.nodes[j+1]));
                        if(hint!=null){ detail=hint+"   "+detail;break; }
                    }
                    if(warning.isEmpty() && meters<=Math.max(45,Math.abs(truck.optDouble("speed"))*5)
                            && route.spoken<i&&!truck.optBoolean("paused")) {
                        route.spoken=i;speak(step.cue,Math.max(10,Math.round(meters/10f)*10),false);
                    }
                }
            }
        }
        if(truck!=null&&!truck.optBoolean("paused")) {
            double allowed=truck.optDouble("limit",-1);
            boolean over=allowed>0 && Math.abs(truck.optDouble("speed"))-allowed>2.2;
            if(over&&!speeding&&warning.isEmpty()&&SystemClock.elapsedRealtime()-lastSpeedWarning>12000) {
                speak(VoiceCue.SPEED,0,false);lastSpeedWarning=SystemClock.elapsedRealtime();speeding=true;
            } else if(!over) speeding=false;
        }
        String destination=truck==null?"":truck.optString("delivery");
        String remaining=numeric("distance",.001," km");
        double seconds=truck==null?-1:truck.optDouble("seconds",-1);
        double scale=truck==null?-1:truck.optDouble("localScale",-1);
        if (realTime) seconds=scale>0?seconds/scale:-1;
        long minutes=seconds<0?-1:Math.round(seconds/60);
        String eta=minutes<0?"—":String.format(PT,"%dh %02dm",minutes/60,minutes%60);
        if(mapView!=null) {
            mapView.route=route;mapView.stops=new ArrayList<>(stops);mapView.hazards=alerts;
            mapView.snapshot(truck);
            maneuver.setText(turn);maneuverDetail.setText(detail);
            hazard.setText(warning);hazard.setVisibility(warning.isEmpty()?View.GONE:View.VISIBLE);
            speed.setText(numeric("speed",3.6,""));limit.setText("Limite "+numeric("limit",3.6,""));
            if(route!=null && !freightRoute) {
                destination="Destino no mapa";
                remaining=Math.round(route.cumulative[route.nodes.length-1]-route.progress)+" m";
                eta="—";
            }
            fuelGauge.setText(numeric("fuel",1," L"));
            tripBar.setText((destination.isEmpty()?"Viagem":destination)+"  ·  "+remaining+"  ·  "+(realTime?"REAL ≈ ":"SIM ")+eta);
            mapCaption.setText(!demo&&!mapStatus.isEmpty()?mapStatus:
                map==null?"Somente rastro · aguardando mapa de estradas":map.name+" · mapa no dispositivo");
        }
        if(tripDetails!=null) {
            tripDetails.setText((destination.isEmpty()?"Sem entrega ativa":destination)+"\n"
                +(truck==null?"—":truck.optString("cargo","—"))+"\nDistância  "+remaining+"   Tempo  "+eta
                +"\nCombustível  "+numeric("fuel",1," L")+" / "+numeric("fuelCapacity",1," L")
                +"\nMarcha  "+(truck==null?"—":truck.optString("gear","—"))
                +"   Rotação  "+numeric("rpm",1," rpm")+"\nPiloto automático  "+numeric("cruise",3.6," km/h")
                +"\nDesgaste do motor  "+numeric("wear",100,"%")+"\nHodômetro  "+numeric("odometer",1," km")
                +"\nPagamento  "+numeric("income",1," €"));
        }
    }

    void toast(String message) { if(!isDestroyed())Toast.makeText(this,message,Toast.LENGTH_SHORT).show(); }
    void discover() {
        connection.setText("Procurando computadores na rede…");
        commands.execute(() -> {
            List<HubConnection> found;
            try {found=HubConnection.discover();}catch(Exception e){found=Collections.emptyList();}
            List<HubConnection> devices=found;
            ui.post(() -> {
                if(isDestroyed())return;
                connection.setText(hub==null?"Selecione um Max Hub":"Max Hub · "+hub.name);
                AlertDialog.Builder dialog=new AlertDialog.Builder(this).setTitle("Conectar ao Max Hub");
                if(devices.isEmpty()) dialog.setMessage("Nenhum PC encontrado. Abra o Max Hub e confira se os dois dispositivos estão na mesma rede.");
                else {
                    String[] names=new String[devices.size()];
                    for(int i=0;i<names.length;i++) names[i]=devices.get(i).name+" · "+devices.get(i).origin.getHost();
                    dialog.setItems(names,(d,i)->enterCode(devices.get(i)));
                }
                dialog.setPositiveButton(devices.isEmpty()?"Buscar de novo":"Atualizar",(d,i)->discover())
                    .setNeutralButton("Endereço manual",(d,i)->manual()).setNegativeButton("Fechar",null).show();
            });
        });
    }

    boolean openPairLink(Intent intent) {
        android.net.Uri uri=intent.getData();
        if(uri==null || !"maxgps".equals(uri.getScheme()) || !"parear".equals(uri.getHost())) return false;
        List<String> parts=uri.getPathSegments();
        String code=uri.getQueryParameter("codigo");
        if(parts.size()!=2 || !HubConnection.privateIp(parts.get(0)) || !parts.get(1).matches("[0-9]{1,5}")
                || code==null || !code.matches("[0-9]{6}")) return false;
        int port=Integer.parseInt(parts.get(1));
        if(port<1 || port>65535)return false;
        HubConnection device=new HubConnection(parts.get(0),port,"",parts.get(0));
        new AlertDialog.Builder(this).setTitle("Parear com "+parts.get(0)+"?")
            .setNegativeButton("Cancelar",null).setPositiveButton("Conectar",(d,i)->commands.execute(()->{
                try {HubConnection paired=device.pair(code);ui.post(()->{if(!isDestroyed())connect(paired);});}
                catch(Exception e){ui.post(()->toast("Falha ao parear. Abra um novo QR no Hub."));}
            })).show();
        return true;
    }

    void enterCode(HubConnection device) {
        EditText code=new EditText(this);
        code.setSingleLine(true);code.setHint("000000");code.setInputType(InputType.TYPE_CLASS_NUMBER);
        code.setFilters(new android.text.InputFilter[]{new android.text.InputFilter.LengthFilter(6)});
        LinearLayout wrap=stack(true);inset(wrap,20);wrap.addView(code);
        AlertDialog dialog=new AlertDialog.Builder(this).setTitle(device.name)
            .setMessage("Digite o código de 6 dígitos mostrado no Max Hub do PC.").setView(wrap)
            .setPositiveButton("Parear",null).setNegativeButton("Cancelar",null).create();
        dialog.setOnShowListener(event->dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(view->{
            String entered=code.getText().toString();
            if(!entered.matches("[0-9]{6}")){code.setError("Digite os 6 dígitos.");return;}
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setEnabled(false);
            commands.execute(()->{
                try {
                    HubConnection paired=device.pair(entered);
                    ui.post(()->{if(!isDestroyed()){dialog.dismiss();connect(paired);}});
                }catch(Exception bad){
                    ui.post(()->{if(!isDestroyed()&&dialog.isShowing()){code.setError(bad.getMessage());dialog.getButton(AlertDialog.BUTTON_POSITIVE).setEnabled(true);}});
                }
            });
        }));
        dialog.show();
    }

    void manual() {
        EditText address=new EditText(this);
        address.setSingleLine(true);address.setInputType(InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_URI);
        address.setHint("http://192.168.1.10:8765/?chave=…");
        LinearLayout wrap=stack(true);inset(wrap,20);wrap.addView(address);
        AlertDialog dialog=new AlertDialog.Builder(this).setTitle("Endereço manual")
            .setMessage("Cole o endereço completo exibido em Conexão manual no Max Hub.").setView(wrap)
            .setPositiveButton("Conectar",null).setNegativeButton("Cancelar",null).create();
        dialog.setOnShowListener(event->dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(view->{
            HubConnection selected=HubConnection.parse(address.getText().toString());
            if(selected==null){address.setError("Use o endereço completo da rede local.");return;}
            dialog.dismiss();connect(selected);
        }));
        dialog.show();
    }

    void connect(HubConnection selected) {
        hub=selected;demo=false;truck=null;scope="";alertScope="";alertRevision=-1;announced.clear();alerts=new JSONArray();
        settings.edit().putString("hub",selected.address()).putString("hub_name",selected.name).apply();
        setMap(null,"");
        connection.setText("Conectando a "+selected.name+"…");
        display();
    }

    void buildSettings() {
        LinearLayout column=section(body);
        vertical(column,text("Ajustes",25,INK,true),0);
        String[] outputs={"Silencioso","Celular","PC do Hub"};
        String[] values={"off","local","pc"};
        int current=Arrays.asList(values).indexOf(voiceOutput);
        vertical(column,button("Áudio · "+outputs[Math.max(0,current)],()->new AlertDialog.Builder(this)
            .setTitle("Saída dos avisos").setSingleChoiceItems(outputs,current,(dialog,index)->{
                if(tts!=null)tts.stop();
                voiceSequence++;voiceBusy=false;releaseAudio();
                if(!voiceOutput.equals(values[index]))voice="";
                voiceOutput=values[index];saveVoice();dialog.dismiss();select(3);
            }).setNegativeButton("Fechar",null).show()),12);
        vertical(column,button(voice.isEmpty()?"Escolher voz":voice,this::chooseVoice),8);
        vertical(column,button("Velocidade e tom",this::tuneVoice),8);
        vertical(column,button("Testar voz",()->speak(VoiceCue.CAMERA,0,true)),8);
        voiceStatus=text(voiceMessage,13,MINT,false);
        vertical(column,voiceStatus,5);
        vertical(column,button("Instalar voz no Android",this::installVoice),8);
        vertical(column,button(demo?"Encerrar demonstração":"Demonstração de navegação",this::changeDemo),18);
        if(hub!=null)vertical(column,button("Desconectar do PC",()->{
            hub=null;truck=null;alertScope="";alertRevision=-1;alerts=new JSONArray();announced.clear();
            settings.edit().remove("hub").remove("hub_name").apply();
            connection.setText("PC desconectado");select(3);
        }),8);
    }

    void saveVoice() {
        settings.edit().putString("voice_output",voiceOutput).putString("voice_name",voice)
            .putFloat("voice_rate",speechRate).putFloat("voice_pitch",speechPitch).apply();
    }

    void chooseVoice() {
        if(voiceOutput.equals("off")) {toast("Selecione uma saída de áudio primeiro.");return;}
        if(voiceOutput.equals("pc")) {
            if(hub==null){toast("Conecte o PC primeiro.");return;}
            HubConnection active=hub;
            commands.execute(()->{
                try {
                    JSONArray choices=active.json("/vozes",null).optJSONArray("voices");
                    ArrayList<String> names=new ArrayList<>();
                    if(choices!=null)for(int i=0;i<choices.length();i++)names.add(choices.getString(i));
                    ui.post(()->voiceDialog(names));
                }catch(Exception e){ui.post(()->toast("Vozes do PC indisponíveis."));}
            });
        } else {
            ArrayList<String> names=new ArrayList<>();
            Set<Voice> installed=speechReady?tts.getVoices():null;
            if(installed!=null)for(Voice item:installed)
                if(!item.isNetworkConnectionRequired() && (item.getFeatures()==null||!item.getFeatures().contains("notInstalled"))) names.add(item.getName());
            Collections.sort(names);
            voiceDialog(names);
        }
    }

    void voiceDialog(List<String> names) {
        if(isDestroyed())return;
        ArrayList<String> choices=new ArrayList<>(names);choices.add(0,"Padrão");
        new AlertDialog.Builder(this).setTitle("Escolher voz").setItems(choices.toArray(new String[0]),(d,i)->{
            voice=i==0?"":choices.get(i);saveVoice();select(3);
        }).show();
    }

    void tuneVoice() {
        LinearLayout panel=stack(true);inset(panel,18);
        panel.addView(text("Velocidade",15,INK,true));
        android.widget.SeekBar rate=new android.widget.SeekBar(this);rate.setMax(9);rate.setProgress(Math.round((speechRate-.6f)*10));panel.addView(rate);
        panel.addView(text("Tom no celular",15,INK,true));
        android.widget.SeekBar pitch=new android.widget.SeekBar(this);pitch.setMax(9);pitch.setProgress(Math.round((speechPitch-.6f)*10));panel.addView(pitch);
        new AlertDialog.Builder(this).setTitle("Ajustar voz").setView(panel).setPositiveButton("Salvar",(d,i)->{
            speechRate=.6f+rate.getProgress()/10f;speechPitch=.6f+pitch.getProgress()/10f;saveVoice();
        }).setNegativeButton("Cancelar",null).show();
    }

    AudioAttributes audioAttributes() {
        return new AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_MEDIA)
            .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH).build();
    }
    void initializeSpeech() {
        if(tts!=null) tts.shutdown();
        speechReady=false;
        tts=new TextToSpeech(this,result -> ui.post(() -> {
            if(isDestroyed()||tts==null)return;
            speechReady=result==TextToSpeech.SUCCESS;
            if(!speechReady)return;
            tts.setAudioAttributes(audioAttributes());
            tts.setOnUtteranceProgressListener(new UtteranceProgressListener() {
                @Override public void onStart(String id) {ui.post(()->{if(isCurrentVoice(id)&&speakingTest)voiceNotice("O Android começou a narrar.");});}
                @Override public void onDone(String id) {ui.post(()->{if(isCurrentVoice(id)&&speakingTest)voiceNotice("Teste de voz concluído no celular.");});}
                @Override public void onError(String id) {voiceFailed(id);}
                @Override public void onError(String id,int code) {voiceFailed(id);}
            });
        }));
    }
    void voiceNotice(String message) {voiceMessage=message;if(voiceStatus!=null)voiceStatus.setText(message);}
    boolean isCurrentVoice(String identifier) {return Integer.toString(voiceSequence).equals(identifier);}
    void voiceFailed(String id) {
        ui.post(()->{if(isCurrentVoice(id)) playOnPhoneFromHub(speakingPhrase,speakingTest,voiceSequence);});
    }
    void installVoice() {
        try {startActivity(new Intent(TextToSpeech.Engine.ACTION_INSTALL_TTS_DATA));installingVoice=true;}
        catch(ActivityNotFoundException ignored){voiceNotice("Ative um mecanismo de texto para fala nos ajustes do Android.");}
    }
    void releaseAudio() {
        if(audio!=null){audio.release();audio=null;}
        if(audioClip!=null){audioClip.delete();audioClip=null;}
    }
    void speak(VoiceCue cue,int meters,boolean test) {
        String phrase=cue.phrase(PT,meters);
        if(!visible) return;
        if(voiceOutput.equals("off")){if(test)voiceNotice("Selecione Celular ou PC do Hub.");return;}
        if(voiceBusy&&!test)return;
        int sequence=++voiceSequence;
        if(test)voiceNotice("Preparando áudio…");
        if(voiceOutput.equals("pc")) {
            HubConnection active=hub;
            if(active==null){if(test)voiceNotice("Conecte ao Max Hub no PC.");return;}
            JSONObject payload=json("text",phrase,"rate",speechRate,"voice",voice);
            voiceBusy=true;
            voiceNetwork.execute(()->{
                String message;
                try {message=active.json(test?"/voz/teste":"/voz",payload).optString("notice","Aviso enviado ao PC.");}
                catch(Exception failure){message=failure.getMessage()==null?"O Hub não confirmou a reprodução.":failure.getMessage();}
                String status=message;
                ui.post(()->{if(sequence==voiceSequence){voiceBusy=false;if(test)voiceNotice(status);}});
            });
            return;
        }
        speakingPhrase=phrase;speakingTest=test;
        boolean available=false;
        if(speechReady && tts!=null) {
            Set<Voice> installed=tts.getVoices();
            if(!voice.isEmpty()&&installed!=null)for(Voice item:installed)
                if(item.getName().equals(voice)){available=tts.setVoice(item)==TextToSpeech.SUCCESS;break;}
            if(!available)available=tts.setLanguage(PT)>=TextToSpeech.LANG_AVAILABLE;
            tts.setSpeechRate(speechRate);tts.setPitch(speechPitch);
        }
        releaseAudio();
        String localized=available && tts.getVoice()!=null?cue.phrase(tts.getVoice().getLocale(),meters):phrase;
        if(!available||tts.speak(localized,TextToSpeech.QUEUE_FLUSH,null,Integer.toString(sequence))!=TextToSpeech.SUCCESS)
            playOnPhoneFromHub(phrase,test,sequence);
    }

    void playOnPhoneFromHub(String phrase,boolean test,int sequence) {
        HubConnection active=hub;
        if(active==null){if(test)voiceNotice("Instale uma voz em português no Android ou conecte ao Hub para usar a voz do PC no celular.");return;}
        if(voiceBusy)return;
        if(test)voiceNotice("Buscando a voz do Hub para reproduzir no celular…");
        voiceBusy=true;
        JSONObject payload=json("text",phrase,"rate",speechRate);
        voiceNetwork.execute(()->{
            try {
                byte[] wav=active.request("/voz/audio",payload,5*1024*1024);
                File clip=new File(getCacheDir(),"aviso-max-gps-"+sequence+".wav");
                try(FileOutputStream out=new FileOutputStream(clip)){out.write(wav);}
                ui.post(()->playClip(clip,test,sequence));
            } catch(Exception fail){ui.post(()->{if(sequence==voiceSequence){voiceBusy=false;if(test)voiceNotice("Falha no áudio do Hub. "+fail.getMessage());}});}
        });
    }
    void playClip(File clip,boolean test,int sequence) {
        if(sequence!=voiceSequence||isDestroyed()||!visible){clip.delete();if(sequence==voiceSequence)voiceBusy=false;return;}
        try {
            releaseAudio();audio=new MediaPlayer();audioClip=clip;
            audio.setAudioAttributes(audioAttributes());
            try(FileInputStream input=new FileInputStream(clip)){audio.setDataSource(input.getFD());}
            audio.setOnPreparedListener(player->{player.start();if(test)voiceNotice("Reproduzindo a voz do Hub no celular.");});
            audio.setOnCompletionListener(player->{voiceBusy=false;releaseAudio();clip.delete();if(test)voiceNotice("Teste de voz concluído no celular.");});
            audio.setOnErrorListener((player,code,extra)->{voiceBusy=false;releaseAudio();clip.delete();if(test)voiceNotice("O Android não conseguiu reproduzir o áudio.");return true;});
            audio.prepareAsync();
        }catch(Exception fail){voiceBusy=false;releaseAudio();clip.delete();if(test)voiceNotice("O Android não abriu o áudio recebido.");}
    }

    static JSONObject json(Object... pairs) {
        JSONObject result=new JSONObject();
        try {for(int i=0;i<pairs.length;i+=2)result.put((String)pairs[i],pairs[i+1]);}
        catch(org.json.JSONException ex){throw new IllegalArgumentException(ex);}
        return result;
    }

    void post(String path,JSONObject values) {
        HubConnection active=hub;
        if(active==null){toast("Conecte ao Max Hub.");return;}
        commands.execute(()->{
            try {
                JSONObject answer=active.json(path,values);
                JSONObject media=path.equals("/multimidia")?active.json(path,null):null;
                ui.post(()->{
                    if(isDestroyed()||active!=hub)return;
                    String message=answer.optString("notice");
                    if(media!=null && mediaStatus!=null && tab==2){mediaStatus.setText(message);showMedia(media);}
                    else {if(path.equals("/alertas"))alertRevision=-1;toast(message);}
                });
            }catch(Exception error){ui.post(()->toast("Comando não recebido pelo Hub."));}
        });
    }

    void buildMedia() {
        LinearLayout column=section(body);
        vertical(column,text("Multimídia",25,INK,true),0);
        mediaStatus=text("Controle o tablet do PC pela rede local.",13,MUTED,false);
        vertical(column,mediaStatus,4);
        LinearLayout apps=stack(false);
        item(apps,button("YouTube",()->post("/multimidia",json("action","open","app","youtube"))),5);
        item(apps,button("Spotify",()->post("/multimidia",json("action","open","app","spotify"))),0);
        vertical(column,apps,12);
        LinearLayout other=stack(false);
        item(other,button("YouTube Music",()->post("/multimidia",json("action","open","app","music"))),5);
        item(other,button("Instagram",()->post("/multimidia",json("action","open","app","instagram"))),0);
        vertical(column,other,6);
        addMediaRow(column,new String[]{"Viagem","Apps","Expandir"},new String[]{"trip","apps","expand"});
        addMediaRow(column,new String[]{"Anterior","Tocar / pausar","Próxima"},new String[]{"previous","playpause","next"});
        addMediaRow(column,new String[]{"− Volume","Mudo","+ Volume"},new String[]{"volumedown","mute","volumeup"});
        EditText query=new EditText(this);query.setSingleLine(true);query.setHint("Artista ou vídeo");
        query.setFilters(new android.text.InputFilter[]{new android.text.InputFilter.LengthFilter(100)});
        vertical(column,query,10);
        LinearLayout buttons=stack(false);
        item(buttons,button("Buscar",()->post("/multimidia",json("action","search","query",query.getText().toString().trim()))),5);
        item(buttons,button("Falar",this::recognize),0);
        vertical(column,buttons,6);
        mediaResults=stack(true);vertical(column,mediaResults,8);
        HubConnection active=hub;
        if(active!=null)commands.execute(()->{
            try{JSONObject data=active.json("/multimidia",null);ui.post(()->{if(tab==2&&active==hub)showMedia(data);});}
            catch(Exception ignored){}
        });
    }
    void addMediaRow(LinearLayout column,String[] names,String[] actions) {
        LinearLayout row=stack(false);
        for(int i=0;i<names.length;i++){String action=actions[i];item(row,button(names[i],()->post("/multimidia",json("action",action))),i==names.length-1?0:5);}
        vertical(column,row,7);
    }
    void showMedia(JSONObject media) {
        if(mediaResults==null||isDestroyed())return;
        mediaResults.removeAllViews();
        JSONArray rows=media.optJSONArray("results");
        if(rows==null)return;
        for(int i=0;i<rows.length();i++){
            JSONObject result=rows.optJSONObject(i);
            if(result==null)continue;
            int pick=i+1;
            vertical(mediaResults,button(pick+". "+result.optString("title"),()->post("/multimidia",
                json("action","result","index",pick,"query",media.optString("query")))),5);
        }
    }
    void recognize() {
        Intent intent=new Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH);
        intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL,RecognizerIntent.LANGUAGE_MODEL_FREE_FORM);
        intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE,"pt-BR");
        intent.putExtra(RecognizerIntent.EXTRA_PROMPT,"Diga: Ok Max, procure um artista");
        try{startActivityForResult(intent,SPEECH);}
        catch(ActivityNotFoundException error){toast("Reconhecimento de voz indisponível neste celular.");}
    }
    @Override protected void onActivityResult(int request,int result,Intent data) {
        super.onActivityResult(request,result,data);
        if(request!=SPEECH||result!=RESULT_OK||data==null)return;
        ArrayList<String> words=data.getStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS);
        if(words!=null&&!words.isEmpty())post("/multimidia",json("action","voice","phrase",words.get(0)));
    }

    static String labelAlert(String type) {
        if(type.equals("radar"))return "Radar";
        if(type.equals("bump"))return "Quebra-molas";
        return "Fiscalização cadastrada";
    }
    void markAlert() {
        if(demo||truck==null){toast("Entre na cabine no ETS2 para marcar um alerta.");return;}
        String[] types={"radar","police","bump"};
        new AlertDialog.Builder(this).setTitle("Marcar a posição do caminhão")
            .setItems(new String[]{"Radar","Fiscalização cadastrada","Quebra-molas"},(d,i)->
                post("/alertas",json("action","add","scope",scope,"type",types[i]))).show();
    }
    void manageAlerts() {
        if(demo){toast("Saia da demonstração para editar suas marcações.");return;}
        ArrayList<JSONObject> points=new ArrayList<>();
        ArrayList<String> names=new ArrayList<>();
        for(int i=0;i<alerts.length();i++){
            JSONObject point=alerts.optJSONObject(i);
            if(point==null||point.optString("id").startsWith("map-"))continue;
            points.add(point);names.add(labelAlert(point.optString("type"))+" · "+Math.round(point.optDouble("x"))+" / "+Math.round(point.optDouble("z")));
        }
        if(points.isEmpty()){toast("Nenhuma marcação pessoal neste mapa.");return;}
        new AlertDialog.Builder(this).setTitle("Escolha uma marcação para remover").setItems(names.toArray(new String[0]),(dialog,index)->
            new AlertDialog.Builder(this).setMessage("Remover esta marcação?").setNegativeButton("Cancelar",null)
                .setPositiveButton("Remover",(d,i)->post("/alertas",json("action","delete","scope",scope,"id",points.get(index).optString("id")))).show()).show();
    }

    void changeDemo() {
        demo=!demo;truck=null;announced.clear();alertScope="";alertRevision=-1;alerts=new JSONArray();
        if(demo){
            demoStart=SystemClock.elapsedRealtime();
            try {
                JSONObject circuit=json("version",1,"name","Circuito de demonstração",
                    "nodes",new JSONArray("[[0,300],[0,0],[320,0],[320,-280],[690,-280],[690,300]]"),
                    "roads",new JSONArray("[[0,1,1],[1,2,1],[2,3,1],[3,4,1],[4,5,1],[5,0,1]]"),
                    "lanes",new JSONArray("[[1,2,2,2]]"),
                    "places",new JSONArray().put(json("type","fuel","x",320,"z",0))
                        .put(json("type","company","city","demo","company","depot","x",690,"z",-280)));
                RoadMap sample=new RoadMap(circuit);
                setMap(sample,"demo");
                alerts.put(json("id","demo-r","type","radar","x",0,"z",140,"heading",0));
                alerts.put(json("id","demo-b","type","bump","x",190,"z",0,"heading",-.25));
                alerts.put(json("id","demo-p","type","police","x",320,"z",-145,"heading",0));
            }catch(Exception invalid){throw new IllegalStateException(invalid);}
            connection.setText("Demonstração");
        }else{
            setMap(null,"");
            connection.setText(hub==null?"Procurar o Max Hub":"Conectando ao Max Hub…");
        }
        select(0);
    }

    static JSONObject demoTruck(double seconds) {
        double[][] points={{0,300},{0,0},{320,0},{320,-280},{690,-280},{690,300},{0,300}};
        double progress=seconds*22%2540;
        for(int i=1;i<points.length;i++){
            double[] a=points[i-1],b=points[i];
            double dx=b[0]-a[0],dz=b[1]-a[1],length=Math.hypot(dx,dz);
            if(progress<=length || i==points.length-1){
                double ratio=Math.min(progress/length,1);
                return json("x",a[0]+dx*ratio,"z",a[1]+dz*ratio,"heading",-Math.atan2(dx,-dz)/(Math.PI*2),
                    "speed",22,"limit",25,"distance",86000,"seconds",3900,"localScale",19,"fuel",417,"fuelCapacity",640,
                    "cruise",22,"odometer",23108,"wear",.028,"gear",11,"rpm",1360,"income",21850,
                    "cargo","Equipamentos","cityId","demo","companyId","depot","delivery","Centro de distribuição");
            }
            progress-=length;
        }
        return null;
    }
}
