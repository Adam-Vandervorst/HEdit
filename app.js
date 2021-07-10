/*
An editor for H's, T's, and (rich) graphs.
Copyright (C) 2020  Adam Vandervorst

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/
*/

'use strict';

function isTouch(e) {
    try {
        return e.sourceCapabilities.firesTouchEvents
    } catch (error) {
        return ('ontouchstart' in window) || (navigator.MaxTouchPoints > 0) || (navigator.msMaxTouchPoints > 0)
    }
}

function genFileName(h) {
    let date = 'D' + (new Date()).toISOString().slice(0, 10).replace(/-/g,"");
    let graph = h ? `${h.name}N${h.nodes.length}E${h.edges.length}` : ''
    return graph + date + ".json"
}

function download(filename, text) {
    let element = document.createElement('a');
    element.setAttribute('href', 'data:text/plain;charset=utf-8,' + encodeURIComponent(text));
    element.setAttribute('download', filename);
    element.style.display = 'none';

    document.body.appendChild(element);
    element.click();
    document.body.removeChild(element);
}

function upload(func) {
    let element = document.createElement('input');
    element.setAttribute('type', 'file');
    element.addEventListener('change', evt => {
        let r = new FileReader();
        r.onload = e => func({name: element.value.match(/([^\\]+$)/g)[0], content: e.target.result})
        r.readAsText(evt.target.files[0]);
    }, false);
    element.style.display = 'none';

    document.body.appendChild(element);
    element.click();
    document.body.removeChild(element);
}

function toggle_show(el) {
    let cur = el.style.display;
    if (cur === '') {el.style.display = 'none'}
    else {el.style.display = ''}
}

function show(node_edge) {
    return JSON.stringify(node_edge.id)
}

function remove(xs, y) {
    let i = xs.indexOf(y);
    if (i === -1) return false;
    xs.splice(i, 1);
    return true;
}

function mod(x, m) {
    return (x % m + m) % m;
}

function randBetween(low, high) {
    return Math.floor(Math.random()*(high - low + 1)) + low;
}

function std(array) {
    let n = array.length, mean = array.reduce((a, b) => a+b)/n;
    return Math.sqrt(array.map(x => Math.pow(x-mean, 2)).reduce((a, b) => a+b)/n);
}

function lightness(rgb) {
    let [r, g, b] = rgb;
    return (0.299*r + 0.587*g + 0.114*b)/255;
}

let _test_canvas = document.createElement('canvas'), _test_ctx = _test_canvas.getContext("2d");
_test_canvas.width = 1; _test_canvas.height = 1; _test_ctx.font = "15px sans-serif";
function colorToRgb(str) {
    // TODO add hsl black
    if (['black', 'rgb(0,0,0)', '#000', '#000000'].includes(str)) return [0, 0, 0];
    _test_ctx.fillStyle = "rgb(0,0,0)";
    _test_ctx.fillStyle = str;
    if (_test_ctx.fillStyle === "#000000" || str == null) return null;
    _test_ctx.fillRect(0, 0, 1, 1);
    return _test_ctx.getImageData(0, 0, 1, 1).data.slice(0, 3)
}

function rgbToHex(rgb) {
    return '#' + Array.from(rgb).map(x => Math.min(Math.round(x), 255).toString(16).padStart(2, '0')).join('');
}

function hexToRgb(hex) {
    let bigint = parseInt(hex[0] == '#' ? hex.substring(1) : hex, 16);
    return [(bigint >> 16) & 255, (bigint >> 8) & 255, bigint & 255]
}

function randomColor() {
    let rgb = [0, 0, 0];
    do rgb = rgb.map(() => randBetween(20, 255));
    while (lightness(rgb) > .7 || std(rgb) < 10);
    return rgb;
}

function middle(...pn) {
    let xs = pn.map(p => p.x), ys = pn.map(p => p.y);
    return [(Math.max(...xs) + Math.min(...xs))/2, (Math.max(...ys) + Math.min(...ys))/2]
}

function dist(p1, p2) {
    return Math.sqrt(Math.pow(p1.x - p2.x, 2) + Math.pow(p1.y - p2.y, 2))
}

function onSameSide(a, b, c, d) {
    let det = (x1, y1, x2, y2) => x1*y2 - y1*x2
    let px = d.x - c.x,
        py = d.y - c.y;
    let l = det(px, py, a.x - c.x, a.y - c.y),
        m = det(px, py, b.x - c.x, b.y - c.y);
    return l*m >= 0
}

function edgeEq(id1, id2) {
    if (Array.isArray(id1) && Array.isArray(id2)) return edgeEq(id1[0], id2[0]) && edgeEq(id1[1], id2[1]);
    else return id1 === id2;
}

function edgeContains(id, item) {
    if (edgeEq(id, item)) return true;
    if (Array.isArray(id)) return edgeContains(id[0], item) || edgeContains(id[1], item);
    return false;
}

function edgeConvert(eid) {
    if (isNaN(eid)) return [edgeConvert(eid['src']), edgeConvert(eid['dst'])];
    return eid;
}

function* expand(f, seed, max_iter=Number.MAX_SAFE_INTEGER, cond=x => (Array.isArray(x) ? x.length : x)) {
    yield seed;
    for (let last = seed, i = 0; i < max_iter && cond(last); i++)
        yield (last = f(last));
}

function representatives(a, extract=x => x) {
    let features = {};
    return a.filter(e => !features[extract(e)] && (features[extract(e)] = true))
}


class Node {
    constructor(point, name, id, color) {
        this.max_width = 90; this.height = 40;
        this.x = point.x; this.y = point.y;
        this.name = name; this.id = id;
        this.color = color || (random_color ? colors[id % colors.length] : default_node_color);
    }

    is_interior(point) {
        return Math.pow(point.x - this.x, 2)/Math.pow(this.width/2, 2) +
               Math.pow(point.y - this.y, 2)/Math.pow(this.height/2, 2) <= 1
    }

    draw(ctx) {
        let a = .7, b = .9;
        ctx.beginPath();
        ctx.moveTo(this.x - this.width/2, this.y);
        ctx.bezierCurveTo(
            this.x - this.width/2, this.y + b*this.height/2,
            this.x - a*this.width/2, this.y + this.height/2,
            this.x, this.y + this.height/2);
        ctx.bezierCurveTo(
            this.x + a*this.width/2, this.y + this.height/2,
            this.x + this.width/2, this.y + b*this.height/2,
            this.x + this.width/2, this.y);
        ctx.bezierCurveTo(
            this.x + this.width/2, this.y - b*this.height/2,
            this.x + a*this.width/2, this.y - this.height/2,
            this.x, this.y - this.height/2);
        ctx.bezierCurveTo(
            this.x - a*this.width/2, this.y - this.height/2,
            this.x - this.width/2, this.y - b*this.height/2,
            this.x - this.width/2, this.y);    
        ctx.closePath();
        ctx.fillStyle = this.color;
        ctx.fill();
        if (this.selected) {
            ctx.lineWidth = 4;
            ctx.strokeStyle = "#F99";
            ctx.stroke();
        }

        ctx.font = "15px sans-serif";
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        if (this.selected) {
            ctx.fillStyle = "#f99";
            ctx.fillRect(this.x - this.text_width/2 - 3, this.y - 11, this.text_width + 6, 15 + 5);
            ctx.fillStyle = "#001";
            ctx.fillText(this.name, this.x, this.y);
        } else {
            ctx.fillStyle = "#bbb";
            ctx.fillText(this.display_name, this.x, this.y);
        }
    }

    set name(v) {
        let text_bb = _test_ctx.measureText(v);
        let display_name = v;
        this.data = v;
        this.text_width = text_bb.width;
        while (text_bb.width > this.max_width) {
            display_name = display_name.slice(0, display_name.length - 2) + '-';
            text_bb = _test_ctx.measureText(display_name);
        }
        this.display_name = display_name;
        this.width = Math.max(text_bb.width + 10, this.height);
    }

    get name() {
        return this.data;
    }

    serialize() {
        let base = {id: this.id, data: this.data},
            position = {x: Math.round(this.x), y: Math.round(this.y)};
        if (this.color == default_node_color) return {...base, ...position};
        else return {...base, color: this.color.substr(1), ...position};
    }
}

class Edge {
    constructor(src, dst) {
        this.width = 6; this.radius = 20;
        this.name = `(${src.name}, ${dst.name})`;
        this.src = src; this.dst = dst;
        this.colors = [];
    }

    is_interior(point) {
        let top = {x: this.x + this.radius*Math.sin(-this.θ), y: this.y + this.radius*Math.cos(this.θ)}
        if (this.src === this.dst) return dist({x: this.x, y: this.y}, point) < 2*this.radius;
        return onSameSide(point, this.src, top, this.dst)
            && onSameSide(point, top, this.src, this.dst)
            && onSameSide(point, this.dst, this.src, top);
    }

    draw(ctx) {
        let [sw, cw, sm, cm, sr, cr, sl, cl] = [this.width/2, this.radius].flatMap(c =>
            [this.θ, -this.θ].flatMap(a => [Math.sin, Math.cos].map(f => c*f(a))))

        if (this.selected) { // outside
            ctx.beginPath();
            ctx.moveTo(this.src.x + sm, this.src.y + cm)
            ctx.lineTo(this.x + sl/4, this.y + cl/4)
            ctx.lineTo(this.dst.x + sm, this.dst.y + cm)
            ctx.lineWidth = 8;
            ctx.strokeStyle = "#F99";
            ctx.stroke();
        }

        if (this.selected) { // curvy part
            ctx.beginPath();
            ctx.moveTo(this.x + sm + cr, this.y + cm + sr);
            ctx.bezierCurveTo(
                this.x + sl, this.y + cl,
                this.x - sr, this.y + cr,
                this.x + sm - cr, this.y + cm - sr);
            ctx.lineWidth = 8;
            ctx.strokeStyle = "#F99";
            ctx.stroke();
        }

        ctx.beginPath();
        ctx.moveTo(this.src.x, this.src.y);
        ctx.lineTo(this.src.x + sm, this.src.y + cm);
        ctx.lineTo(this.x + sm + cr, this.y + cm + sr);
        ctx.bezierCurveTo(
            this.x + sl, this.y + cl,
            this.x - sr, this.y + cr,
            this.x + sm - cr, this.y + cm - sr);
        ctx.lineTo(this.dst.x + sm, this.dst.y + cm);
        ctx.lineTo(this.dst.x, this.dst.y);
        ctx.closePath();
        ctx.fillStyle = this.color;
        ctx.fill();

        if (this.selected) { // inside
            ctx.beginPath();
            ctx.moveTo(this.src.x + .5*sm, this.src.y + .5*cm)
            ctx.lineTo(this.dst.x + .5*sm, this.dst.y + .5*cm)
            ctx.lineWidth = 4;
            ctx.strokeStyle = "#F99";
            ctx.stroke();
        }

        let n = this.colors.length;
        this.colors.forEach((c, i) => {
            ctx.beginPath();
            ctx.moveTo(this.x, this.y);
            ctx.arc(this.x, this.y, this.radius/2, this.θ + (i/n)*Math.PI, this.θ + ((i + 1)/n)*Math.PI);
            ctx.lineTo(this.x, this.y);
            ctx.closePath();
            ctx.fillStyle = rgbToHex(c);
            ctx.fill();
        })
    }

    get id() {return [this.src.id, this.dst.id]}
    get x() {return (this.src.x + this.dst.x - (this.src === this.dst ? 3 : 1)*this.radius*Math.sin(this.θ))/2}
    get y() {return (this.src.y + this.dst.y + (this.src === this.dst ? 3 : 1)*this.radius*Math.cos(this.θ))/2}
    get θ() {return Math.atan2(this.src.y - this.dst.y, this.src.x - this.dst.x)}
    get color() {
        let o = this.θ > 0, n = this.colors.length;
        if (n == 0) return o ? default_edge_color : default_edge_color_alt;
        return rgbToHex(this.colors.reduce((ct, c) =>
                [ct[0] + c[0]/n, ct[1] + c[1]/n, ct[2] + c[2]/n], [o, o, o]
        ))
    }

    serialize() {
        return this.id;
    }
}

class H {
    constructor(name, mode) {
        this.deserialize = this.deserialize.bind(this);
        this.name = name || "New";
        this.dx = 0; this.dy = 0;
        this.node_count = 0;
        this.nodes = []; this.edges = [];
        this.buffer = []; this.history = []; this.selected = [];
        this.modes = ['H', 'T', 'property_graph', 'edge_colored_graph', 'graph']
        this.mode = mode == null || !this.modes.includes(mode) ? 1 : this.modes.indexOf(mode);
    }

    restore(c) {this.focus(this.dx, this.dy, c)}
    focus(x, y, c) {let t_matrix = c.getTransform(); c.translate(x - t_matrix.e/t_matrix.a, y - t_matrix.f/t_matrix.d); this.dx = x; this.dy = y}
    move(dx, dy, c) {this.dx += 30*dx; this.dy += 30*dy; c.translate(30*dx, 30*dy)}
    scale(f) {let [x, y] = middle(...this.nodes); this.nodes.forEach(n => {n.x = (n.x - x)*(1+f)+x; n.y = (n.y - y)*(1+f)+y})}
    tighten() {this.mode = Math.min(this.mode + 1, this.modes.length - 1)}
    loosen() {this.mode = Math.max(this.mode - 1, 0)}
    redo() {if (this.buffer.length) {let step = this.buffer.pop(); step.do(); this.history.push(step)}}
    undo() {if (this.history.length) {let step = this.history.pop(); step.undo(); this.buffer.push(step)}}

    spawnNode(p) {
        let new_node = new Node(p, this.name + this.node_count, this.node_count);
        let step = {do: () => this.nodes.push(new_node),
                    undo: () => remove(this.nodes, new_node),
                    str: `Spawn node '${new_node.name}' at ${p.x}, ${p.y}`}
        step.do(); this.node_count++;
        this.history.push(step);
    }

    delete_selected() {
        let to_be_deleted = new Set(this.selected), last_size = -1;
        while (to_be_deleted.size !== last_size) {
            last_size = to_be_deleted.size;
            to_be_deleted.forEach(i => this.edges.forEach(e => (e.dst === i || e.src === i) && to_be_deleted.add(e)));
        }

        let step = {do: () => to_be_deleted.forEach(i => {remove(this.selected, i); i instanceof Edge ? remove(this.edges, i) : remove(this.nodes, i)}),
                    undo: () => to_be_deleted.forEach(i => i instanceof Edge ? this.edges.push(i) : this.nodes.push(i)),
                    str: `Delete ${[...to_be_deleted].map(show).join(', ')}`}
        step.do();
        this.history.push(step);
    }

    rename_selected() {
        let nodes_atm = this.selected.filter(i => i instanceof Node);
        let old_names = nodes_atm.map(n => n.name);
        let new_names = nodes_atm.map(n => prompt("Rename " + n.name) || n.name)
        let step = {do: () => nodes_atm.forEach((n, i) => n.name = new_names[i]),
                    undo: () => nodes_atm.forEach((n, i) => n.name = old_names[i]),
                    str: `Rename ${nodes_atm.map(show).join(', ')}`}
        step.do();
        this.history.push(step);
    }

    color_selected() {
        let nodes_atm = this.selected.filter(i => i instanceof Node);
        let old_colors = nodes_atm.map(n => n.color);
        let new_color_str = prompt("Enter a CSS color for the selection");
        let new_color_rgb = colorToRgb(new_color_str);
        if (new_color_rgb == null) return console.log("invalid CSS color");
        let new_color = rgbToHex(new_color_rgb);
        let step = {do: () => nodes_atm.forEach(n => n.color = new_color),
                    undo: () => nodes_atm.forEach((n, i) => n.color = old_colors[i]),
                    str: `Color ${nodes_atm.map(show).join(', ')} ${new_color_str}`}
        step.do()
        this.history.push(step);
    }

    recolor_selected() {
        let nodes_atm = this.selected.filter(i => i instanceof Node);
        let old_colors = nodes_atm.map(n => n.color);
        let new_colors = nodes_atm.map(_ => rgbToHex(randomColor()))
        let step = {do: () => nodes_atm.forEach((n, i) => n.color = new_colors[i]),
                    undo: () => nodes_atm.forEach((n, i) => n.color = old_colors[i]),
                    str: `Recolor ${nodes_atm.map(show).join(', ')}`}
        step.do()
        this.history.push(step);
    }

    move_selected() {
        let nodes_atm = this.selected.filter(i => i instanceof Node), nn = nodes_atm.length;
        let [mx, my] = middle(...nodes_atm);
        return (new_point, node_edge) => {
            if (node_edge) return;
            let [dx, dy] = [new_point.x - mx, new_point.y - my];
            let step = {do: () => nodes_atm.forEach(n => {n.x += dx; n.y += dy}),
                        undo: () => nodes_atm.forEach(n => {n.x -= dx; n.y -= dy}),
                        str: `Move ${nodes_atm.map(show).join(', ')}`};
            step.do();
            this.history.push(step);
        }
    }

    replace_selected() {
        let selected_atm = this.selected.slice();
        let to_replace = [], referenced = [], by = [];
        this.edges.forEach(e => selected_atm.forEach(i => {
            if (i === e.src) {to_replace.push(i); referenced.push(e); by.push("src")}
            if (i === e.dst) {to_replace.push(i); referenced.push(e); by.push("dst")}
        }))
        return (new_point, node_edge) => {
            if (!node_edge) return;
            let step = {do: () => referenced.forEach((e, ind) => e[by[ind]] = node_edge),
                        undo: () => referenced.forEach((e, ind) => e[by[ind]] = to_replace[ind]),
                        str: `Replaced ${selected_atm.map(show).join(', ')} by ${show(node_edge)}`};
            step.do();
            this.history.push(step);
        }
    }

    walk_selected(outgoing = true) {
        let selected_atm = this.selected.slice();
        let newly_selected = selected_atm.flatMap(item => item instanceof Node ?
            this.edges.filter(e => e[outgoing ? "src" : "dst"] === item) : item[outgoing ? "dst" : "src"])
            .filter((v, i, a) => a.indexOf(v) == i);
        let step = {do: () => {this.selected.forEach(i => i.selected = false); (this.selected = newly_selected).forEach(i => i.selected = true)},
                    undo: () => {this.selected.forEach(i => i.selected = false); (this.selected = selected_atm).forEach(i => i.selected = true)},
                    str: `Walk ${selected_atm.map(show).join(', ')} to ${[outgoing ? "outgoing" : "incoming"]} (${newly_selected.map(show).join(', ')})`};
        step.do();
        this.history.push(step);
    }

    connect_selected() {
        let selected_atm = this.selected.slice();
        return (new_point, node_edge) => {
            if (!node_edge) return;
            let edges = selected_atm.filter(i => this.can_connect(i, node_edge)).map(i => new Edge(i, node_edge));
            let step = {do: () => this.edges.push(...edges),
                        undo: () => this.edges = this.edges.filter(e => !edges.includes(e)),
                        str: `Connect ${selected_atm.map(show).join(', ')} to ${show(node_edge)}`};
            step.do();
            this.history.push(step);
        }
    }

    tag_selected() {
        let selected_atm = this.selected.slice();
        return (new_point, node_edge) => {
            if (!node_edge) return;
            let edges = selected_atm.filter(i => this.can_connect(node_edge, i)).map(i => new Edge(node_edge, i));
            let step = {do: () => this.edges.push(...edges),
                        undo: () => this.edges = this.edges.filter(e => !edges.includes(e)),
                        str: `Connect ${show(node_edge)} to ${selected_atm.map(show).join(', ')}`};
            step.do();
            this.history.push(step);
        }
    }

    can_connect(src, dst) {
        if (!src || !dst) return false;
        if (this.mode > 0 && src instanceof Edge) return false; // in anything but an H, edges must start from nodes
        if (this.mode >= 4 && dst instanceof Edge) return false; // in a graph edges must point to nodes
        if (this.mode == 3 && dst instanceof Edge && dst.colors.length > 0) return false; // in an edge colored graph edges may only have one property
        if (this.mode >= 2 && dst instanceof Edge && dst.dst instanceof Edge) return false; // in a property graph and an edge colored graph, if an edge points to another edge, that other edge must point to a vertex
        return true;
    }

    connect(src, dst) {
        if (!this.can_connect(src, dst)) return;
        let new_edge = new Edge(src, dst);
        let step = {do: () => this.edges.push(new_edge),
                    undo: () => remove(this.edges, new_edge),
                    str: `Connect ${show(src)} with ${show(dst)}`}
        step.do();
        this.history.push(step);
    }

    select(n) {
        let step = n.selected ? {
            do: () => {remove(this.selected, n); n.selected = false},
            undo: () => {this.selected.push(n); n.selected = true},
            str: `Deselect ${show(n)}`
        } : {
            do: () => {this.selected.push(n); n.selected = true},
            undo: () => {remove(this.selected, n); n.selected = false},
            str: `Select ${show(n)}`
        }
        step.do();
        this.history.push(step);
    }

    deselect() {
        if (!this.selected.length) return;
        let previously_selected = this.selected.slice();
        let step = {do: () => {while (this.selected.length) {this.selected.pop().selected = false}},
                    undo: () => {previously_selected.forEach(i => {i.selected = true; this.selected.push(i)})},
                    str: `Deselect ${this.selected.map(show).join(', ')}`}
        step.do();
        this.history.push(step);
    }

    serialize() {
        return JSON.stringify({
            name: this.name,
            mode: this.modeStr,
            version: 2,
            data: this.nodes.map(n => n.serialize()),
            conn: this.edges.map(e => e.serialize())
        });
    }

    deserializable(obj) {
        if (!('conn' in obj && 'data' in obj))
            throw Error("'conn' and 'data' are necessary for deserialization.");

        if ((obj.version|0) < 2)
            obj.conn = obj.conn.map(edgeConvert);

        obj.name = obj.name || "Unnamed";
        obj.mode = this.modes.includes(obj.mode) ? obj.mode : this.modes[0];
        return obj;
    }

    deserialize(obj) {
        let ser = this.deserializable(obj);
        this.name = ser.name;
        this.mode = this.modes.indexOf(ser.mode);
        this.nodes = ser.data.map(d => new Node(d, d.data, d.id, d.color && '#' + d.color));
        this.edges = [];
        while (ser.conn.length)
            ser.conn = ser.conn.filter(d => {
                let src = this.nodes.find(n => d[0] === n.id) || this.edges.find(e => edgeEq(d[0], e.id));
                let dst = this.nodes.find(n => d[1] === n.id) || this.edges.find(e => edgeEq(d[1], e.id));
                if (src && dst) return this.edges.push(new Edge(src, dst)) && false;
                return true;
            });
        this.node_count = Math.max(...ser.data.map(d => d.id)) + 1;
        return this;
    }

    get modeStr() {return this.modes[this.mode]}
}

class Board {
    constructor(start_h) {
        this.draw = this.draw.bind(this);
        this.handleInteraction = this.handleInteraction.bind(this);
        this.keypressHandler = this.keypressHandler.bind(this);
        this.canvas = container.firstElementChild;
        this.c = this.canvas.getContext('2d');
        this.resetCanvas();

        this.hs = [start_h]; this.h = this.hs[0];
        this.show_gray = true; this.show_disconnected = true;
        this.only_outgoing = false; this.only_incoming = false;
        this.touch = null;

        window.addEventListener("keydown", this.keypressHandler);

        this.canvas.addEventListener("mousedown", e => {if (!isTouch(e)) this.touch = {
            x: e.x - this.h.dx, y: e.y - this.h.dy,
            start_t: window.performance.now()
        }}, false)
        this.canvas.addEventListener("mouseup", e => {if (!isTouch(e)) {this.touch = {
            x: e.x - this.h.dx, y: e.y - this.h.dy,
            alt: window.performance.now() - this.touch.start_t > 300 || e.button === 2,
            static: Math.hypot(this.touch.x - e.x + this.h.dx, this.touch.y - e.y + this.h.dy) < 5,
            hit_color: rgbToHex(this.c.getImageData(e.x*this.sx|0, e.y*this.sy|0, 1, 1).data.slice(0, 3))
        }; this.handleInteraction()}}, false)
        this.canvas.addEventListener("touchstart", e => {let t = e.changedTouches[0]; this.touch = {
            x: t.clientX - this.h.dx, y: t.clientY  - this.h.dy,
            start_t: window.performance.now()
        }}, {passive: true});
        this.canvas.addEventListener("touchend", e => {let t = e.changedTouches[0]; this.touch = {
            x: t.clientX - this.h.dx, y: t.clientY - this.h.dy,
            alt: window.performance.now() - this.touch.start_t > 300,
            static: Math.hypot(this.touch.x - t.clientX + this.h.dx, this.touch.y - t.clientY + this.h.dy) < 5,
            hit_color: rgbToHex(this.c.getImageData(t.clientX*this.sx|0, t.clientY*this.sy|0, 1, 1).data.slice(0, 3))
        }; this.handleInteraction()}, {passive: true});

        this.canvas.addEventListener('contextmenu', e => e.preventDefault(), false)
        if (this.h.nodes.length) {
            for (let m of welcome_messages) m.style.display = "none";
            this.keypressHandler({key: "h"});
            this.keypressHandler({key: " "});
        }
    }

    get sx() {return this.canvas.width/parseInt(this.canvas.style.width, 10)}
    get sy() {return this.canvas.height/parseInt(this.canvas.style.height, 10)}

    resetCanvas() {
        // HiDPI canvas adapted from http://www.html5rocks.com/en/tutorials/canvas/hidpi/
        let devicePixelRatio = window.devicePixelRatio || 1;
        this.canvas.width = window.innerWidth*devicePixelRatio;
        this.canvas.height = window.innerHeight*devicePixelRatio;
        this.canvas.style.width = window.innerWidth + 'px';
        this.canvas.style.height = window.innerHeight + 'px';
        this.c.scale(devicePixelRatio, devicePixelRatio);
    }

    keypressHandler(e) {
        switch (e.key) {
            case "0": this.h.delete_selected(); break;
            case "1": this.h.rename_selected(); break;
            case "2": this.h.recolor_selected(); break;
            case "3": this.partial = this.h.move_selected(); break;
            case "4": this.partial = this.h.replace_selected(); break;
            case "5": this.partial = this.h.connect_selected(); break;
            case "6": this.partial = this.h.tag_selected(); break;
            case "7": this.h.color_selected(); break;
            case "s": download(genFileName(this.h), this.h.serialize()); break;
            case "l": upload(file => this.hs.push(new H().deserialize(JSON.parse(file.content))) && this.update_open() && this.draw()); break;
            case "f": {let name = prompt("Find node by name"), res = this.h.nodes.find(n => n.name === name); if (res) this.h.focus(this.canvas.width/2 - res.x, this.canvas.height/2 - res.y, this.c) || this.draw()} break;
            case "F": {let sid = prompt("Find node by id"), res = this.h.nodes.find(n => String(n.id) === sid); if (res) this.h.focus(this.canvas.width/2 - res.x, this.canvas.height/2 - res.y, this.c) || this.draw()} break;
            case "w": this.h.walk_selected(true); break;
            case "W": this.h.walk_selected(false); break;
            case "c": this.only_outgoing = !this.only_outgoing; break;
            case "C": this.only_incoming = !this.only_incoming; break;
            case "n": this.h.name = prompt("Rename " + this.h.name) || this.h.name; this.update_open(); break;
            case "g": this.show_gray = !this.show_gray; break;
            case "d": this.show_disconnected = !this.show_disconnected; break;
            case "h": toggle_show(commands); break;
            case "H": toggle_show(history); break;
            case "i": toggle_show(information); break;
            case "m": this.h.tighten(); break;
            case "M": this.h.loosen(); break;
            case "r": this.resetCanvas(); this.keypressHandler({key: " "}); break;
            case "u": this.h.undo(); break;
            case "U": this.h.redo(); break;
            case "+": this.h.scale(.2); break;
            case "-": this.h.scale(-.2); break;
            case "ArrowUp": if (e.shiftKey) {this.h = this.hs[mod(this.hs.indexOf(this.h) - 1, this.hs.length)]; this.h.restore(this.c); this.update_open()}
                            else this.h.move(0, -1, this.c); break;
            case "ArrowDown": if (e.shiftKey) {this.h = this.hs[mod(this.hs.indexOf(this.h) + 1, this.hs.length)]; this.h.restore(this.c); this.update_open()}
                            else this.h.move(0, 1, this.c); break;
            case "ArrowLeft": if (e.shiftKey) {let hi = this.hs.indexOf(this.h); if (hi > 0) {this.hs.splice(hi, 1); this.h = this.hs[hi - 1]} this.update_open()}
                            else this.h.move(-1, 0, this.c); break;
            case "ArrowRight": if (e.shiftKey) {this.h = new H(prompt("Name new H")); this.hs.push(this.h); this.update_open(); this.h.focus(0, 0, this.c)}
                            else this.h.move(1, 0, this.c); break;
            case " ": let [mx, my] = middle(...this.h.nodes); this.h.focus(this.canvas.width/2 - mx, this.canvas.height/2 - my, this.c); break;
            case "Escape": {this.partial = null; this.h.deselect()} break;
            default: return;
        }
        window.requestAnimationFrame(this.draw);
        if (e.stopPropagation) {e.stopPropagation(); e.preventDefault()}
    }

    handleInteraction() {
        let [vns, ves] = this.visible();
        let on_edge = ves.find(e => dist(e, this.touch) <= e.radius/2
                                || (e.is_interior(this.touch) && e.color === this.touch.hit_color));
        let on_node = vns.find(n => n.is_interior(this.touch));

        if (this.touch.static) {
            if (this.touch.alt && !on_node && !on_edge)
                this.h.spawnNode(this.touch);
            else {
                if (this.partial) this.partial = this.partial(this.touch, on_node || on_edge);
                else if (on_node || on_edge) this.h.select(on_node || on_edge);
                else this.h.deselect();
            }
        }

        window.requestAnimationFrame(this.draw);
    }

    update_information() {
        [
            this.h.name,
            this.h.modeStr,
            this.only_incoming && this.only_outgoing ? "both" : !this.only_incoming && !this.only_outgoing ? "all" :
                this.only_incoming ? "incoming" : "outgoing",
            this.h.selected.map(show).join(', '),
            this.h.nodes.length,
            this.h.edges.length,
            this.h.edges.filter(e => e.colors.length).length
        ].forEach((v, i) => information.rows[i + 1].cells[1].innerHTML = v)
    }

    update_history() {
        for (let r = 1, l = this.h.history.length; r < history.rows.length; r++) {
            let step = this.h.history[l - r], row = history.rows[r];
            row.cells[0].innerHTML = step ? l - r : '';
            row.cells[1].innerHTML = step ? step.str : '';
        }
    }

    update_open() {
        open.innerHTML = ''
        this.hs.forEach((h, i) => {
            let open_h = document.createElement('li');
            open_h.innerHTML = h.name;
            if (h === this.h) open_h.className = 'selected';
            open.appendChild(open_h);
        })
    }

    propagate_colors() {
        this.h.edges.forEach(e => e.colors.length = 0);
        this.h.edges.forEach(e => (e.dst instanceof Edge) && e.dst.colors.push(hexToRgb(e.src.color)))
    }

    visible() {
        let ns, es;

        if (this.h.selected.length && (this.only_incoming || this.only_outgoing)) {
            let match = (this.only_incoming && this.only_outgoing) ? (i => e => edgeEq(e.src.id, i.id) || edgeEq(e.dst.id, i.id)):
                this.only_outgoing ? i => e => edgeEq(e.src.id, i.id) : i => e => edgeEq(e.dst.id, i.id);
            let initial = this.h.selected.flatMap(item => [item, ...this.h.edges.filter(match(item))]);
            let nested_duplicates = Array.from(expand(is => is.filter(i => i instanceof Edge).flatMap(e =>
                    [e.src, e.dst].filter(edgep => !is.includes(edgep))), initial));
            let shown = representatives(nested_duplicates.flatMap(x => x), item => JSON.stringify(item.id));
            ns = shown.filter(i => i instanceof Node);
            es = shown.filter(i => i instanceof Edge);
        } else {
            ns = this.h.nodes.slice();
            es = this.h.edges.slice().reverse();
        }

        if (!this.show_gray)
            es = es.filter(e => e.colors.length || this.h.selected.includes(e));

        if (!this.show_disconnected)
            ns = ns.filter(n => es.find(e => n === e.src || n === e.dst) || this.h.selected.includes(n));

        ns.sort((x, y) => x.id - y.id);
        es.sort((x, y) => edgeContains(y.id, x.id) - edgeContains(x.id, y.id));
        return [ns, es]
    }

    draw() {
        this.c.save();
        this.c.setTransform(1, 0, 0, 1, 0, 0);
        this.c.clearRect(0, 0, this.canvas.width, this.canvas.height);
        this.c.restore();
        this.propagate_colors();

        if (!history.style.display) this.update_history();
        if (!information.style.display) this.update_information();

        let [vns, ves] = this.visible();
        ves.forEach(e => e.draw(this.c));
        vns.forEach(n => n.draw(this.c));
    }
}

let colors = ['#F3C300', '#875692', '#F38400', '#5f8fbd', '#BE0032', '#dec25f', '#848482', '#018856', '#bd6e88', '#0167A5', '#c67562', '#604E97', '#F6A600', '#B3446C', '#DCD300', '#882D17', '#8DB600', '#654522', '#E25822', '#2B3D26']
let default_node_color = '#101010', default_edge_color = '#888888', default_edge_color_alt = rgbToHex(hexToRgb(default_edge_color).map(c => c > 0 ? c - 1 : 1));
let container = document.getElementById('board'), commands = document.getElementById('commands'), history = document.getElementById('history'), information = document.getElementById('information'), open = document.getElementById('open'), welcome_messages = document.getElementsByClassName("welcome");
let board, random_color = false;

window.addEventListener('resize', () => {
    board.resetCanvas();
    board.keypressHandler({key: " "});
});

let params = new URLSearchParams(window.location.search);
let param = null, param_h = new H(params.get('name'), params.get('mode'));
if (window.location.hash) param_h.deserialize(JSON.parse(decodeURI(window.location.hash.slice(1))));
if (params.has('random_color')) random_color = true;
new Promise((resolve, reject) => {
    if (param = params.get('uri')) fetch(param, {credentials: 'include'})
        .then(response => response.json())
        .then(data => param_h.deserialize(data))
        .finally(() => resolve(board = new Board(param_h)));
    else resolve(board = new Board(param_h));
}).then(ins => {
    if (param = params.get('selected')) JSON.parse(param)
        .map(i => param_h.nodes.find(n => n.id == i) || param_h.edges.find(e => edgeEq(e.id, i)))
        .filter(x => x).forEach(n => param_h.select(n)) || ins.draw();
    if (params.has('hide_help')) ins.keypressHandler({key: "h"});
    if (params.has('show_history')) ins.keypressHandler({key: "H"});
    if (params.has('show_information')) ins.keypressHandler({key: "i"});
    if (params.has('hide_gray')) ins.keypressHandler({key: "g"});
    if (params.has('hide_disconnected')) ins.keypressHandler({key: "d"});
    if (params.has('only_outgoing')) ins.keypressHandler({key: "c"});
    if (params.has('only_incoming')) ins.keypressHandler({key: "C"});
})
