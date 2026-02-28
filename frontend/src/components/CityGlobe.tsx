import { useRef } from 'react'
import { Canvas, useFrame, extend } from '@react-three/fiber'
import { Float, OrbitControls } from '@react-three/drei'
import * as THREE from 'three'

class EarthMaterial extends THREE.ShaderMaterial {
  constructor() {
    super({
      uniforms: {
        uTime: { value: 0 },
      },
      vertexShader: `
        varying vec3 vNormal;
        varying vec3 vPosition;
        varying vec2 vUv;
        void main() {
          vNormal = normalize(normalMatrix * normal);
          vPosition = (modelViewMatrix * vec4(position, 1.0)).xyz;
          vUv = uv;
          gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        }
      `,
      fragmentShader: `
        uniform float uTime;
        varying vec3 vNormal;
        varying vec3 vPosition;
        varying vec2 vUv;

        // simplex-style noise via hash
        vec3 mod289(vec3 x) { return x - floor(x * (1.0/289.0)) * 289.0; }
        vec4 mod289(vec4 x) { return x - floor(x * (1.0/289.0)) * 289.0; }
        vec4 permute(vec4 x) { return mod289(((x*34.0)+1.0)*x); }
        vec4 taylorInvSqrt(vec4 r) { return 1.79284291400159 - 0.85373472095314 * r; }
        vec3 fade(vec3 t) { return t*t*t*(t*(t*6.0-15.0)+10.0); }

        float cnoise(vec3 P) {
          vec3 Pi0 = floor(P);
          vec3 Pi1 = Pi0 + vec3(1.0);
          Pi0 = mod289(Pi0);
          Pi1 = mod289(Pi1);
          vec3 Pf0 = fract(P);
          vec3 Pf1 = Pf0 - vec3(1.0);
          vec4 ix = vec4(Pi0.x, Pi1.x, Pi0.x, Pi1.x);
          vec4 iy = vec4(Pi0.yy, Pi1.yy);
          vec4 iz0 = Pi0.zzzz;
          vec4 iz1 = Pi1.zzzz;
          vec4 ixy = permute(permute(ix) + iy);
          vec4 ixy0 = permute(ixy + iz0);
          vec4 ixy1 = permute(ixy + iz1);
          vec4 gx0 = ixy0 * (1.0/7.0);
          vec4 gy0 = fract(floor(gx0) * (1.0/7.0)) - 0.5;
          gx0 = fract(gx0);
          vec4 gz0 = vec4(0.5) - abs(gx0) - abs(gy0);
          vec4 sz0 = step(gz0, vec4(0.0));
          gx0 -= sz0 * (step(0.0, gx0) - 0.5);
          gy0 -= sz0 * (step(0.0, gy0) - 0.5);
          vec4 gx1 = ixy1 * (1.0/7.0);
          vec4 gy1 = fract(floor(gx1) * (1.0/7.0)) - 0.5;
          gx1 = fract(gx1);
          vec4 gz1 = vec4(0.5) - abs(gx1) - abs(gy1);
          vec4 sz1 = step(gz1, vec4(0.0));
          gx1 -= sz1 * (step(0.0, gx1) - 0.5);
          gy1 -= sz1 * (step(0.0, gy1) - 0.5);
          vec3 g000 = vec3(gx0.x,gy0.x,gz0.x);
          vec3 g100 = vec3(gx0.y,gy0.y,gz0.y);
          vec3 g010 = vec3(gx0.z,gy0.z,gz0.z);
          vec3 g110 = vec3(gx0.w,gy0.w,gz0.w);
          vec3 g001 = vec3(gx1.x,gy1.x,gz1.x);
          vec3 g101 = vec3(gx1.y,gy1.y,gz1.y);
          vec3 g011 = vec3(gx1.z,gy1.z,gz1.z);
          vec3 g111 = vec3(gx1.w,gy1.w,gz1.w);
          vec4 norm0 = taylorInvSqrt(vec4(dot(g000,g000),dot(g010,g010),dot(g100,g100),dot(g110,g110)));
          g000 *= norm0.x; g010 *= norm0.y; g100 *= norm0.z; g110 *= norm0.w;
          vec4 norm1 = taylorInvSqrt(vec4(dot(g001,g001),dot(g011,g011),dot(g101,g101),dot(g111,g111)));
          g001 *= norm1.x; g011 *= norm1.y; g101 *= norm1.z; g111 *= norm1.w;
          float n000 = dot(g000, Pf0);
          float n100 = dot(g100, vec3(Pf1.x, Pf0.yz));
          float n010 = dot(g010, vec3(Pf0.x, Pf1.y, Pf0.z));
          float n110 = dot(g110, vec3(Pf1.xy, Pf0.z));
          float n001 = dot(g001, vec3(Pf0.xy, Pf1.z));
          float n101 = dot(g101, vec3(Pf1.x, Pf0.y, Pf1.z));
          float n011 = dot(g011, vec3(Pf0.x, Pf1.yz));
          float n111 = dot(g111, Pf1);
          vec3 fade_xyz = fade(Pf0);
          vec4 n_z = mix(vec4(n000,n100,n010,n110), vec4(n001,n101,n011,n111), fade_xyz.z);
          vec2 n_yz = mix(n_z.xy, n_z.zw, fade_xyz.y);
          float n_xyz = mix(n_yz.x, n_yz.y, fade_xyz.x);
          return 2.2 * n_xyz;
        }

        void main() {
          float lon = vUv.x * 6.28318 - 3.14159;
          float lat = vUv.y * 3.14159 - 1.5708;
          vec3 spherePos = vec3(cos(lat)*cos(lon), sin(lat), cos(lat)*sin(lon));

          float n1 = cnoise(spherePos * 1.8 + 0.5);
          float n2 = cnoise(spherePos * 3.5 + 2.0) * 0.5;
          float n3 = cnoise(spherePos * 7.0 + 4.0) * 0.25;
          float land = n1 + n2 + n3;
          float landMask = smoothstep(-0.05, 0.08, land);

          vec3 ocean = vec3(0.02, 0.03, 0.08);
          vec3 landColor = vec3(0.04, 0.06, 0.12);
          vec3 baseColor = mix(ocean, landColor, landMask);

          // subtle grid lines
          float latLine = 1.0 - smoothstep(0.0, 0.006, abs(fract(vUv.y * 12.0) - 0.5) - 0.49);
          float lonLine = 1.0 - smoothstep(0.0, 0.006, abs(fract(vUv.x * 24.0) - 0.5) - 0.49);
          float grid = max(latLine, lonLine) * 0.08;
          baseColor += vec3(0.25, 0.28, 0.9) * grid;

          // city lights on land
          float dots = cnoise(spherePos * 30.0);
          float dots2 = cnoise(spherePos * 50.0) * 0.4;
          float cityMask = smoothstep(0.4, 0.58, dots + dots2) * landMask;
          vec3 cityColor = vec3(0.95, 0.85, 0.45);
          baseColor += cityColor * cityMask * 0.8;
          // bright cores
          float coreMask = smoothstep(0.6, 0.75, dots + dots2) * landMask;
          baseColor += vec3(1.0, 0.95, 0.7) * coreMask * 0.6;

          // fresnel rim
          vec3 viewDir = normalize(-vPosition);
          float fresnel = 1.0 - dot(viewDir, vNormal);
          fresnel = pow(fresnel, 2.5);
          baseColor += vec3(0.39, 0.4, 0.95) * fresnel * 0.3;

          gl_FragColor = vec4(baseColor, 1.0);
        }
      `,
    })
  }
}

class GlobeAtmosphereMaterial extends THREE.ShaderMaterial {
  constructor() {
    super({
      uniforms: {
        uColor: { value: new THREE.Color('#6366f1') },
        uIntensity: { value: 0.6 },
      },
      vertexShader: `
        varying vec3 vNormal;
        varying vec3 vPosition;
        void main() {
          vNormal = normalize(normalMatrix * normal);
          vPosition = (modelViewMatrix * vec4(position, 1.0)).xyz;
          gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        }
      `,
      fragmentShader: `
        uniform vec3 uColor;
        uniform float uIntensity;
        varying vec3 vNormal;
        varying vec3 vPosition;
        void main() {
          vec3 viewDir = normalize(-vPosition);
          float fresnel = 1.0 - dot(viewDir, vNormal);
          fresnel = pow(fresnel, 3.0) * uIntensity;
          gl_FragColor = vec4(uColor, fresnel);
        }
      `,
      transparent: true,
      side: THREE.FrontSide,
      depthWrite: false,
    })
  }
}

extend({ EarthMaterial, GlobeAtmosphereMaterial })

declare module '@react-three/fiber' {
  interface ThreeElements {
    earthMaterial: THREE.ShaderMaterial
    globeAtmosphereMaterial: THREE.ShaderMaterial
  }
}

function Globe() {
  const meshRef = useRef<THREE.Mesh>(null)

  useFrame((_, delta) => {
    if (meshRef.current) {
      meshRef.current.rotation.y += delta * 0.06
    }
  })

  return (
    <Float speed={1.5} rotationIntensity={0.2} floatIntensity={0.6}>
      <group>
        <mesh ref={meshRef}>
          <sphereGeometry args={[2, 64, 64]} />
          <earthMaterial />
        </mesh>

        <mesh scale={1.1}>
          <sphereGeometry args={[2, 64, 64]} />
          <globeAtmosphereMaterial />
        </mesh>
      </group>
    </Float>
  )
}

export default function CityGlobe() {
  return (
    <div className="w-full h-[600px]">
      <Canvas
        camera={{ position: [0, 0, 6], fov: 45 }}
        gl={{ antialias: true, alpha: true }}
        style={{ background: 'transparent' }}
      >
        <Globe />
        <OrbitControls
          enableZoom={false}
          enablePan={false}
          autoRotate={false}
          minPolarAngle={Math.PI / 4}
          maxPolarAngle={(3 * Math.PI) / 4}
        />
      </Canvas>
    </div>
  )
}
