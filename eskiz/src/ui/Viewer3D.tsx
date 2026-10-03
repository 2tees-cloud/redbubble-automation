// Настоящий 3D: крутить пальцем, приближать, открывать двери.
// Строится из тех же панелей, что и деталировка (engine/geometry.ts).
import { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import type { Project } from '../engine/furniture';
import { buildScene, type Box } from '../engine/geometry';
import { colorInfo, type Color, type Facade } from '../engine/order';
import FurnitureView from './FurnitureView';

const MM = 0.001; // сцена в метрах
const gloss: Record<Facade, number> = { ldsp: 0.75, mdf_film: 0.6, mdf_paint: 0.45, acrylic: 0.12 };

/** Текстура древесины, нарисованная на лету — без загрузки картинок. */
function woodTexture(hex: string) {
  const c = document.createElement('canvas');
  c.width = 256;
  c.height = 1024;
  const g = c.getContext('2d')!;
  g.fillStyle = hex;
  g.fillRect(0, 0, c.width, c.height);
  let seed = 7;
  const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
  for (let i = 0; i < 70; i++) {
    const x = rnd() * c.width;
    g.strokeStyle = `rgba(60,40,20,${0.04 + rnd() * 0.1})`;
    g.lineWidth = 0.6 + rnd() * 2.2;
    g.beginPath();
    g.moveTo(x, 0);
    for (let y = 0; y <= c.height; y += 64) g.lineTo(x + Math.sin(y / 180 + i) * (4 + rnd() * 6), y);
    g.stroke();
  }
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  return t;
}

type Mover = { group: THREE.Group; box: Box };

interface Props {
  project: Project;
  color: Color;
  facade: Facade;
  worktop?: boolean;
}

export default function Viewer3D(props: Props) {
  const host = useRef<HTMLDivElement>(null);
  const world = useRef<{
    renderer: THREE.WebGLRenderer;
    scene: THREE.Scene;
    camera: THREE.PerspectiveCamera;
    controls: OrbitControls;
    furniture: THREE.Group;
    movers: Mover[];
    open: number;
    target: number;
    fitKey: string;
    fit: () => void;
  } | null>(null);
  const [failed, setFailed] = useState(false);
  const [open, setOpen] = useState(false);
  const [touched, setTouched] = useState(false);

  // Сцена, камера и свет создаются один раз.
  useEffect(() => {
    const el = host.current!;
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: false });
    } catch {
      setFailed(true);
      return;
    }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    el.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    scene.background = new THREE.Color('#efede7');
    const pmrem = new THREE.PMREMGenerator(renderer);
    scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;

    const camera = new THREE.PerspectiveCamera(35, 1, 0.05, 100);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.enablePan = false;
    controls.maxPolarAngle = Math.PI / 2 - 0.04;
    controls.addEventListener('start', () => setTouched(true));

    const sun = new THREE.DirectionalLight('#ffffff', 1.4);
    sun.position.set(-3, 6, 5);
    sun.castShadow = true;
    sun.shadow.mapSize.set(2048, 2048);
    sun.shadow.bias = -0.0005;
    scene.add(sun, sun.target, new THREE.HemisphereLight('#ffffff', '#c9c3b5', 0.6));

    const floor = new THREE.Mesh(new THREE.PlaneGeometry(40, 40), new THREE.ShadowMaterial({ opacity: 0.16 }));
    floor.rotation.x = -Math.PI / 2;
    floor.receiveShadow = true;
    scene.add(floor);

    const furniture = new THREE.Group();
    scene.add(furniture);

    const state = {
      renderer, scene, camera, controls, furniture, movers: [] as Mover[], open: 0, target: 0, fitKey: '',
      fit: () => {
        const box = new THREE.Box3().setFromObject(furniture);
        if (box.isEmpty()) return;
        const sphere = box.getBoundingSphere(new THREE.Sphere());
        const dist = (sphere.radius / Math.sin(THREE.MathUtils.degToRad(camera.fov / 2))) * (camera.aspect < 1 ? 1.25 / camera.aspect : 1.05);
        const dir = new THREE.Vector3(0.42, 0.22, 1).normalize();
        controls.target.copy(sphere.center);
        camera.position.copy(sphere.center).addScaledVector(dir, dist);
        controls.minDistance = sphere.radius * 0.6;
        controls.maxDistance = dist * 2.5;
        // Тень покрывает всю мебель.
        const s = sun.shadow.camera;
        s.left = s.bottom = -sphere.radius * 1.6;
        s.right = s.top = sphere.radius * 1.6;
        sun.position.copy(sphere.center).add(new THREE.Vector3(-2, 6, 4));
        sun.target.position.copy(sphere.center);
        s.updateProjectionMatrix();
        controls.update();
      },
    };
    world.current = state;

    const resize = () => {
      const w = el.clientWidth;
      const h = el.clientHeight;
      renderer.setSize(w, h, false);
      camera.aspect = w / Math.max(1, h);
      camera.updateProjectionMatrix();
    };
    const ro = new ResizeObserver(() => {
      resize();
    });
    ro.observe(el);
    resize();

    renderer.setAnimationLoop(() => {
      // Плавное открытие/закрытие дверей.
      state.open += (state.target - state.open) * 0.12;
      if (Math.abs(state.target - state.open) < 0.001) state.open = state.target;
      for (const { group, box } of state.movers) {
        if (box.hinge) group.rotation.y = (box.hinge === 'left' ? -1 : 1) * state.open * THREE.MathUtils.degToRad(100);
        if (box.slide) group.position.x = (group.userData.baseX as number) + box.slide * MM * state.open;
      }
      controls.update();
      renderer.render(scene, camera);
    });

    return () => {
      ro.disconnect();
      renderer.setAnimationLoop(null);
      controls.dispose();
      disposeGroup(furniture);
      pmrem.dispose();
      scene.environment?.dispose();
      renderer.dispose();
      renderer.domElement.remove();
      world.current = null;
    };
  }, []);

  // Мебель перестраивается при каждом изменении размеров или материала.
  useEffect(() => {
    const w = world.current;
    if (!w) return;
    disposeGroup(w.furniture);
    w.furniture.clear();
    w.movers = [];
    const sc = buildScene(props.project, { doors: true, worktop: props.worktop });
    const base = colorInfo[props.color].swatch;
    const wood = props.color === 'oak' || props.color === 'walnut';
    const tex = wood ? woodTexture(base) : null;
    const mats = new Map<string, THREE.Material>();
    const mat = (key: string, make: () => THREE.Material) => {
      if (!mats.has(key)) mats.set(key, make());
      return mats.get(key)!;
    };
    const materialFor = (b: Box): THREE.Material => {
      switch (b.role) {
        case 'mirror': return mat('mirror', () => new THREE.MeshStandardMaterial({ color: '#e4eef0', metalness: 1, roughness: 0.04 }));
        case 'metal': return mat('metal', () => new THREE.MeshStandardMaterial({ color: '#a3abae', metalness: 0.85, roughness: 0.35 }));
        case 'handle': return mat('handle', () => new THREE.MeshStandardMaterial({ color: '#4d5356', metalness: 0.9, roughness: 0.3 }));
        case 'worktop': return mat('worktop', () => new THREE.MeshStandardMaterial({ color: '#6b645b', roughness: 0.5 }));
        case 'plinth': return mat('plinth', () => new THREE.MeshStandardMaterial({ color: new THREE.Color(base).multiplyScalar(0.75), roughness: 0.8 }));
        case 'back': return mat('back', () => new THREE.MeshStandardMaterial({ color: new THREE.Color(base).multiplyScalar(0.92), roughness: 0.9 }));
        case 'front': {
          const r = gloss[props.facade];
          if (!tex) return mat('front', () => new THREE.MeshStandardMaterial({ color: base, roughness: r }));
          const m = new THREE.MeshStandardMaterial({ map: tex.clone(), roughness: r });
          m.map!.repeat.set(Math.max(1, b.w / 600), Math.max(1, b.h / 1200));
          return m;
        }
        default: {
          if (!tex) return mat('body', () => new THREE.MeshStandardMaterial({ color: base, roughness: 0.75 }));
          const m = new THREE.MeshStandardMaterial({ map: tex.clone(), roughness: 0.75 });
          m.map!.repeat.set(Math.max(1, Math.max(b.w, b.d) / 600), Math.max(1, b.h / 1200));
          return m;
        }
      }
    };
    const edgeMat = new THREE.LineBasicMaterial({ color: '#000000', transparent: true, opacity: 0.18 });

    const mesh = (b: Box) => {
      const geo = new THREE.BoxGeometry(b.w * MM, b.h * MM, b.d * MM);
      const m = new THREE.Mesh(geo, materialFor(b));
      m.castShadow = b.role !== 'mirror';
      m.receiveShadow = true;
      if (b.role !== 'handle') m.add(new THREE.LineSegments(new THREE.EdgesGeometry(geo), edgeMat));
      return m;
    };
    // Центр детали в координатах three: z смотрит на зрителя, поэтому глубина со знаком минус.
    const center = (b: Box) => new THREE.Vector3((b.x + b.w / 2) * MM, (b.y + b.h / 2) * MM, -(b.z + b.d / 2) * MM);

    const groups = new Map<number, THREE.Group>();
    sc.boxes.forEach((b, i) => {
      if (b.door !== undefined && groups.has(b.door)) {
        // Ручка или заполнение — внутрь группы своей двери.
        const g = groups.get(b.door)!;
        const m = mesh(b);
        m.position.copy(center(b).sub(g.userData.origin as THREE.Vector3));
        g.add(m);
        return;
      }
      if (b.hinge || b.slide !== undefined) {
        // Поворот вокруг петель: ось у заднего края двери со стороны петель.
        const pivot = b.hinge
          ? new THREE.Vector3((b.hinge === 'left' ? b.x : b.x + b.w) * MM, 0, -(b.z + b.d) * MM)
          : new THREE.Vector3(0, 0, 0);
        const g = new THREE.Group();
        g.position.copy(pivot);
        g.userData = { origin: pivot.clone(), baseX: pivot.x };
        const m = mesh(b);
        m.position.copy(center(b).sub(pivot));
        g.add(m);
        w.furniture.add(g);
        groups.set(i, g);
        w.movers.push({ group: g, box: b });
        return;
      }
      const m = mesh(b);
      m.position.copy(center(b));
      w.furniture.add(m);
    });
    // Мебель стоит по центру сцены.
    w.furniture.position.set((-sc.width / 2) * MM, 0, (sc.depth / 2) * MM);
    w.furniture.updateMatrixWorld(true);

    const key = `${sc.width}x${sc.height}x${sc.depth}`;
    if (key !== w.fitKey) {
      w.fitKey = key;
      w.fit();
    }
  }, [props.project, props.color, props.facade, props.worktop]);

  useEffect(() => {
    if (world.current) world.current.target = open ? 1 : 0;
  }, [open]);

  if (failed) return <FurnitureView project={props.project} color={props.color} doors worktop={props.worktop} />;

  return (
    <div className="viewer3d">
      <div ref={host} className="viewer3d-canvas" />
      <div className="viewer3d-bar">
        <button onClick={() => setOpen((v) => !v)}>{open ? 'Закрыть двери' : 'Открыть двери'}</button>
        <button
          aria-label="Вернуть вид"
          onClick={() => {
            if (world.current) world.current.fit();
          }}
        >
          ⟲
        </button>
      </div>
      {!touched && <div className="viewer3d-hint">Покрутите пальцем · двумя — приблизить</div>}
    </div>
  );
}

function disposeGroup(g: THREE.Object3D) {
  g.traverse((o) => {
    const m = o as THREE.Mesh;
    m.geometry?.dispose();
    const mat = m.material as THREE.Material | THREE.Material[] | undefined;
    if (Array.isArray(mat)) mat.forEach((x) => x.dispose());
    else if (mat) {
      (mat as THREE.MeshStandardMaterial).map?.dispose();
      mat.dispose();
    }
  });
}
