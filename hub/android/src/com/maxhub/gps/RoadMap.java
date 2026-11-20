package com.maxhub.gps;

import org.json.JSONArray;
import org.json.JSONObject;
import org.json.JSONException;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;
import java.util.PriorityQueue;

final class RoadMap {
    final String name;
    final double[] x, z;
    final int[] from, to;
    final int[][] links;

    RoadMap(JSONObject json) throws JSONException {
        if (json.optInt("version") != 1) throw new JSONException("Mapa incompatível");
        name = json.getString("name");
        JSONArray nodes = json.getJSONArray("nodes"), roads = json.getJSONArray("roads");
        int count = nodes.length();
        if (count < 2 || count > 200000 || roads.length() < 1 || roads.length() > 400000)
            throw new JSONException("Tamanho do mapa inválido");
        x = new double[count];
        z = new double[count];
        int[] sizes = new int[count];
        for (int i=0; i<count; i++) {
            JSONArray node = nodes.getJSONArray(i);
            x[i] = node.getDouble(0);
            z[i] = node.getDouble(1);
            if (!(Math.abs(x[i]) < 1e7 && Math.abs(z[i]) < 1e7)) throw new JSONException("Coordenada inválida");
        }
        from = new int[roads.length()];
        to = new int[roads.length()];
        boolean[] twoWay = new boolean[from.length];
        for (int i=0; i<from.length; i++) {
            JSONArray edge = roads.getJSONArray(i);
            int a = edge.getInt(0), b = edge.getInt(1);
            if (a < 0 || a >= count || b < 0 || b >= count || a == b) throw new JSONException("Estrada inválida");
            from[i] = a;
            to[i] = b;
            sizes[a]++;
            twoWay[i] = edge.getInt(2) == 0;
            if (twoWay[i]) sizes[b]++;
        }
        links = new int[count][];
        for (int i=0; i<count; i++) links[i] = new int[sizes[i]];
        Arrays.fill(sizes,0);
        for (int i=0; i<from.length; i++) {
            int a = from[i], b = to[i];
            links[a][sizes[a]++] = b;
            if (twoWay[i]) links[b][sizes[b]++] = a;
        }
    }

    int nearest(double px, double pz, double range) {
        int node = -1;
        double best = range*range;
        for (int i=0; i<x.length; i++) {
            double dx=x[i]-px, dz=z[i]-pz, length=dx*dx+dz*dz;
            if (length < best) { best=length; node=i; }
        }
        return node;
    }

    double distance(int a, int b) { return Math.hypot(x[a]-x[b],z[a]-z[b]); }

    private static final class Candidate {
        final int node;
        final double cost, priority;
        Candidate(int node, double cost, double priority) { this.node=node; this.cost=cost;this.priority=priority; }
    }

    private List<Integer> find(int start, int destination) {
        if (start == destination) return Collections.singletonList(start);
        double[] cost = new double[x.length];
        int[] parents = new int[x.length];
        Arrays.fill(cost, Double.POSITIVE_INFINITY);
        Arrays.fill(parents, -1);
        PriorityQueue<Candidate> pending = new PriorityQueue<>(Comparator.comparingDouble(c -> c.priority));
        pending.add(new Candidate(start,0,distance(start,destination)));
        cost[start]=0;
        while (!pending.isEmpty() && !Thread.currentThread().isInterrupted()) {
            Candidate candidate=pending.remove();
            int node=candidate.node;
            if (cost[node]!=candidate.cost) continue;
            if (node==destination) break;
            for (int next : links[node]) {
                double nextCost=candidate.cost+distance(node,next);
                if (nextCost>=cost[next]) continue;
                cost[next]=nextCost;
                parents[next]=node;
                pending.add(new Candidate(next,nextCost,nextCost+distance(next,destination)));
            }
        }
        if (parents[destination]<0) return Collections.emptyList();
        List<Integer> path=new ArrayList<>();
        for (int i=destination;i>=0;i=parents[i]) path.add(i);
        Collections.reverse(path);
        return path;
    }

    Route plan(int start, List<Integer> stops) {
        List<Integer> points=new ArrayList<>();
        points.add(start);
        for (int stop:stops) {
            List<Integer> leg=find(start,stop);
            if (leg.isEmpty()) return null;
            points.addAll(leg.subList(1,leg.size()));
            start=stop;
        }
        return points.size() < 2 ? null : new Route(this,points);
    }

    static final class Route {
        final int[] nodes;
        final double[] cumulative;
        final List<Step> steps = new ArrayList<>();
        int segment=0, spoken=-1;
        double progress=0;

        Route(RoadMap map, List<Integer> points) {
            nodes=new int[points.size()];
            cumulative=new double[nodes.length];
            for (int i=0;i<nodes.length;i++) {
                nodes[i]=points.get(i);
                if (i>0) cumulative[i]=cumulative[i-1]+map.distance(nodes[i-1],nodes[i]);
            }
            for (int i=1;i<nodes.length-1;i++) {
                int a=nodes[i-1],b=nodes[i],c=nodes[i+1];
                double ix=map.x[b]-map.x[a], iz=map.z[b]-map.z[a];
                double ox=map.x[c]-map.x[b], oz=map.z[c]-map.z[b];
                double angle=Math.atan2(ix*oz-iz*ox,ix*ox+iz*oz);
                if (Math.abs(angle)>.60)
                    steps.add(new Step(cumulative[i],angle>0 ? "Vire à direita" : "Vire à esquerda",angle>0 ? "↱" : "↰"));
            }
            steps.add(new Step(cumulative[cumulative.length-1],"Destino à frente","⚑"));
        }

        boolean advance(RoadMap map,double x,double z) {
            double best=Double.POSITIVE_INFINITY, along=0;
            int bestSegment=segment;
            for (int i=Math.max(0,segment-1);i<Math.min(nodes.length-1,segment+10);i++) {
                int a=nodes[i],b=nodes[i+1];
                double dx=map.x[b]-map.x[a],dz=map.z[b]-map.z[a], length2=dx*dx+dz*dz;
                if (length2==0) continue;
                double t=Math.max(0,Math.min(1,((x-map.x[a])*dx+(z-map.z[a])*dz)/length2));
                double distance=Math.hypot(x-map.x[a]-t*dx,z-map.z[a]-t*dz);
                if (distance<best) { best=distance; bestSegment=i; along=cumulative[i]+t*Math.sqrt(length2); }
            }
            if (best>85) return false;
            segment=Math.max(segment,bestSegment);
            progress=Math.max(progress,along);
            return true;
        }
    }

    static final class Step {
        final double at;
        final String text, glyph;
        Step(double at, String text, String glyph) { this.at=at;this.text=text;this.glyph=glyph; }
    }
}
