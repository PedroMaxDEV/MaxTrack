package com.maxhub.gps;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Matrix;
import android.graphics.Rect;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.Path;
import android.view.GestureDetector;
import android.view.MotionEvent;
import android.view.ScaleGestureDetector;
import android.view.View;
import org.json.JSONArray;
import org.json.JSONObject;
import java.util.ArrayDeque;
import java.util.Collections;
import java.util.List;

final class MapView extends View {
    interface PinListener { void choose(double x, double z); }
    private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Path path = new Path();
    private final GestureDetector gestures;
    private final ScaleGestureDetector pinch;
    private final PinListener onPin;
    private final ArrayDeque<double[]> trail = new ArrayDeque<>();
    private final float density;
    RoadMap map;
    RoadMap.Route route;
    List<Integer> stops=Collections.emptyList();
    JSONArray hazards=new JSONArray();
    private JSONObject truck;
    private double cx,cz;
    private float zoom, bearing, touchAngle;
    private boolean tilted=true;
    private final Matrix viewMatrix=new Matrix(), inverse=new Matrix();
    private final Rect clip=new Rect();
    private final Matrix perspective=new Matrix();

    void tilt() { tilted=!tilted; invalidate(); }

    private void projection() {
        float ax=getWidth()*.5f, ay=getHeight()*.58f;
        viewMatrix.setTranslate(-ax,-ay);
        viewMatrix.postRotate(bearing);
        if (tilted && getHeight()>0) {
            perspective.setValues(new float[]{1,0,0, 0,.78f,0, 0,-.55f/getHeight(),1});
            viewMatrix.postConcat(perspective);
        }
        viewMatrix.postTranslate(ax,ay);
        viewMatrix.invert(inverse);
    }
    private boolean follow=true;
    boolean selecting=false;

    MapView(Context context, PinListener listener) {
        super(context);
        setContentDescription("Mapa do Max GPS. Arraste para navegar e use dois dedos para ampliar.");
        onPin=listener;
        density=getResources().getDisplayMetrics().density;
        zoom=.44f*density;
        gestures=new GestureDetector(context,new GestureDetector.SimpleOnGestureListener() {
            @Override public boolean onDown(MotionEvent motion) { return true; }
            @Override public boolean onScroll(MotionEvent start,MotionEvent end,float dx,float dy) {
                if (!pinch.isInProgress() && end.getPointerCount()==1) {
                    projection();
                    float[] point={end.getX(),end.getY(),end.getX()+dx,end.getY()+dy};
                    inverse.mapPoints(point);
                    follow=false;cx+=(point[2]-point[0])/zoom;cz+=(point[3]-point[1])/zoom;invalidate();
                }
                return true;
            }
            @Override public boolean onSingleTapUp(MotionEvent event) {
                if (selecting) {
                    projection(); float[] point={event.getX(),event.getY()}; inverse.mapPoints(point);
                    onPin.choose(cx+(point[0]-getWidth()*.5)/zoom,cz+(point[1]-getHeight()*.58)/zoom);
                }
                performClick();
                return true;
            }
        });
        pinch=new ScaleGestureDetector(context,new ScaleGestureDetector.SimpleOnScaleGestureListener() {
            @Override public boolean onScale(ScaleGestureDetector scale) {
                zoom(scale.getScaleFactor());
                return true;
            }
        });
    }

    @Override public boolean onTouchEvent(MotionEvent event) {
        if (event.getPointerCount()==2) {
            float angle=(float)Math.toDegrees(Math.atan2(event.getY(1)-event.getY(),event.getX(1)-event.getX()));
            if(event.getActionMasked()==MotionEvent.ACTION_MOVE) {
                follow=false; bearing+=angle-touchAngle; invalidate();
            }
            touchAngle=angle;
        }
        pinch.onTouchEvent(event);
        gestures.onTouchEvent(event);
        return true;
    }
    @Override public boolean performClick() { return super.performClick(); }

    void center() {
        follow=true;
        if(truck!=null) { cx=truck.optDouble("x");cz=truck.optDouble("z"); }
        invalidate();
    }

    void zoom(float factor) {
        zoom=Math.max(.018f*density,Math.min(4*density,zoom*factor));
        invalidate();
    }

    void setMap(RoadMap graph) {
        map=graph;
        route=null;
        stops=Collections.emptyList();
        clearTrail();
        if(truck==null && graph!=null) { cx=graph.x[0];cz=graph.z[0]; }
        invalidate();
    }

    void clearTrail() { trail.clear(); }

    void snapshot(JSONObject truck) {
        this.truck=truck;
        if (truck!=null) {
            double x=truck.optDouble("x"),z=truck.optDouble("z");
            double[] last=trail.peekLast();
            if (last==null || Math.hypot(last[0]-x,last[1]-z)>3) {
                if (trail.size()>=350) trail.removeFirst();
                trail.addLast(new double[]{x,z});
            }
            if (follow) { cx=x;cz=z;bearing=(float)truck.optDouble("heading",0)*360; }
        }
        invalidate();
    }

    float sx(double x) { return (float)(getWidth()*.5+(x-cx)*zoom); }
    float sy(double z) { return (float)(getHeight()*.58+(z-cz)*zoom); }

    private void ink(int color) { paint.setColor(color);paint.setStyle(Paint.Style.FILL); }

    @Override protected void onDraw(Canvas canvas) {
        super.onDraw(canvas);
        canvas.drawColor(0xff252d39);
        canvas.save();
        projection();canvas.concat(viewMatrix);canvas.getClipBounds(clip);
        if (map!=null) {
            path.reset();

            for (int i=0;i<map.from.length;i++) {
                int a=map.from[i],b=map.to[i];
                float x1=sx(map.x[a]),y1=sy(map.z[a]),x2=sx(map.x[b]),y2=sy(map.z[b]);
                if ((x1<clip.left && x2<clip.left) || (y1<clip.top && y2<clip.top) || (x1>clip.right && x2>clip.right) || (y1>clip.bottom && y2>clip.bottom)) continue;
                path.moveTo(x1,y1);path.lineTo(x2,y2);
            }
            stroke(canvas,0xff476580,5);
            for (RoadMap.Place place:map.places) {
                if (place.type.equals("company")) continue;
                float px=sx(place.x),py=sy(place.z);
                if (!clip.contains((int)px,(int)py)) continue;
                canvas.save(); canvas.translate(px,py);canvas.rotate(-bearing);
                ink(0xff296a57);canvas.drawRoundRect(-10*density,-8*density,10*density,8*density,3*density,3*density,paint);
                ink(Color.WHITE); paint.setTextSize(10*density);paint.setTextAlign(Paint.Align.CENTER);
                canvas.drawText(place.type.equals("fuel")?"P":place.type.equals("rest")?"Z":"OF",0,3*density,paint);
                canvas.restore();
            }
        }
        path.reset();
        boolean first=true;
        for (double[] p:trail) {
            if(first) path.moveTo(sx(p[0]),sy(p[1])); else path.lineTo(sx(p[0]),sy(p[1]));
            first=false;
        }
        stroke(canvas,0xff4c8498,2);
        if (route!=null && map!=null) {
            path.reset();
            for (int i=0;i<route.nodes.length;i++) {
                int node=route.nodes[i];
                float x=sx(map.x[node]), y=sy(map.z[node]);
                if (i==0) path.moveTo(x,y); else path.lineTo(x,y);
            }
            stroke(canvas,0xff102637,10);stroke(canvas,0xff18dffa,7);
            ink(0xffc8fff7);
            for(int stop:stops) canvas.drawCircle(sx(map.x[stop]),sy(map.z[stop]),6*density,paint);
        }
        for(int i=0;i<hazards.length();i++) {
            JSONObject marker=hazards.optJSONObject(i);
            if(marker==null) continue;
            float x=sx(marker.optDouble("x")),y=sy(marker.optDouble("z"));
            if(!clip.contains((int)x,(int)y)) continue;
            ink(0xffffc676);
            canvas.drawCircle(x,y,10*density,paint);
            ink(0xff352213);paint.setTextAlign(Paint.Align.CENTER);paint.setTextSize(10*density);
            String type=marker.optString("type");
            canvas.drawText(type.equals("radar")?"R":type.equals("bump")?"Q":"F",x,y+3*density,paint);
        }
        if(truck!=null) {
            canvas.save();
            canvas.translate(sx(truck.optDouble("x")),sy(truck.optDouble("z")));
            canvas.rotate((float)-truck.optDouble("heading")*360);
            canvas.scale(density,density);
            ink(0xff046bc9);
            canvas.drawCircle(0,0,20,paint);
            path.reset();path.moveTo(0,-13);path.lineTo(10,10);path.lineTo(0,6);path.lineTo(-10,10);path.close();
            ink(Color.WHITE);
            canvas.drawPath(path,paint);
            canvas.restore();
        }
        canvas.restore();
    }

    private void stroke(Canvas canvas,int color,float width) {
        paint.setColor(color);paint.setStyle(Paint.Style.STROKE);paint.setStrokeWidth(width*density);
        paint.setStrokeJoin(Paint.Join.ROUND);paint.setStrokeCap(Paint.Cap.ROUND);
        canvas.drawPath(path,paint);
    }
}
